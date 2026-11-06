"""HTTP hardening: security headers and a small rate limiter.

Rate limiting is in-process (a sliding window per key). That is correct for the single
instance this runs on; with more replicas the same interface would be backed by Redis
(DECISIONS.md D-025).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.domain.errors import DomainError

# Strict CSP for the SPA. Inline *style attributes* are needed (React style props for the
# coverage bars), inline *scripts* are not. Swagger UI loads from a CDN, so /api/docs is
# exempt (it's documentation, not the app).
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
    "frame-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'self'; "
    "frame-ancestors 'none'"
)
_DOCS = ("/api/docs", "/api/openapi.json", "/docs/oauth2-redirect")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, hsts: bool) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if not request.url.path.startswith(_DOCS):
            h.setdefault("Content-Security-Policy", CSP)
        if self.hsts:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path.startswith("/api/"):
            h.setdefault("Cache-Control", "no-store")
        return response


class TooManyRequests(DomainError):
    status_code = 429
    code = "rate_limited"
    title = "Too many requests"


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float) -> None:
        self.limit, self.window = limit, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            retry = int(self.window - (now - q[0])) + 1
            raise TooManyRequests(
                f"Too many attempts. Please wait {retry} seconds and try again.",
                details={"retryAfter": retry},
            )
        q.append(now)
        if len(self._hits) > 50_000:  # bound memory under abuse
            self._hits.clear()

    def reset(self) -> None:
        self._hits.clear()


login_limiter = SlidingWindowLimiter(limit=10, window_s=60)  # per IP + email
ai_limiter = SlidingWindowLimiter(limit=20, window_s=60)  # per user: protects LLM spend


def client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers, so this is the real client behind Render's proxy.
    return request.client.host if request.client else "unknown"


# --- upload content sniffing --------------------------------------------------------
_MAGIC = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}


def content_matches_type(content: bytes, content_type: str) -> bool:
    """Never trust the client's Content-Type: check the file's magic bytes."""
    sigs = _MAGIC.get(content_type)
    return bool(sigs) and any(content.startswith(s) for s in sigs)
