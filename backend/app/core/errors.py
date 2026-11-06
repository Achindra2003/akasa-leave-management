"""Map every error to RFC 9457 Problem Details (application/problem+json).

Shape:
    {"type": "...#overlapping_leave", "title": "...", "status": 409,
     "detail": "<friendly, user-facing sentence>", "code": "overlapping_leave",
     "fields": {"toDate": "..."}, "requestId": "..."}
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import log, request_id_var
from app.domain.errors import DomainError, OverlappingLeave, StaleRequest

PROBLEM = "application/problem+json"


def problem(
    status: int, code: str, title: str, detail: str, extra: dict[str, Any] | None = None
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://akasa-leave/errors#{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "requestId": request_id_var.get(),
    }
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


_FIELD_NAMES = {"from_date": "fromDate", "to_date": "toDate"}


def _friendly_pydantic(err: dict[str, Any]) -> tuple[str, str]:
    loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path", "form")]
    field = _FIELD_NAMES.get(loc[-1], loc[-1]) if loc else "request"
    etype = err.get("type", "")
    if etype == "missing":
        msg = "This field is required."
    elif etype.startswith("date"):
        msg = "Please enter a valid date (YYYY-MM-DD)."
    else:
        msg = str(err.get("msg", "Invalid value.")).removeprefix("Value error, ")
    return field, msg


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        extra = dict(exc.details)
        return problem(exc.status_code, exc.code, exc.title, exc.message, extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = dict(_friendly_pydantic(e) for e in exc.errors())
        return problem(
            422,
            "validation_failed",
            "Some details need fixing",
            "Please fix the highlighted fields.",
            {"fields": fields},
        )

    @app.exception_handler(StaleDataError)
    async def _stale(_: Request, __: StaleDataError) -> JSONResponse:
        e = StaleRequest(
            "This request was just updated by someone else. Refresh to see the latest status."
        )
        return problem(e.status_code, e.code, e.title, e.message)

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        if "no_overlapping_active_leave" in str(exc.orig):
            e = OverlappingLeave("You already have a leave request covering some of these dates.")
            return problem(e.status_code, e.code, e.title, e.message)
        log.warning("integrity_error", error=str(exc.orig))
        return problem(409, "conflict", "Conflict", "This change conflicts with existing data.")

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        if exc.status_code == 404 and detail == "Not Found":
            detail = "We couldn't find what you were looking for."
        return problem(exc.status_code, f"http_{exc.status_code}", "Request failed", detail)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error=repr(exc))
        return problem(
            500,
            "internal_error",
            "Something went wrong",
            "Something went wrong on our side. Please try again; if it keeps happening, "
            "share the request ID with support.",
        )
