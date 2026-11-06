"""Application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import admin, auth, leaves
from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine, get_sessionmaker
from app.core.errors import register_error_handlers
from app.core.logging import RequestContextMiddleware, configure_logging, log


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.seed_demo_data:
        from app.seed import seed

        async with get_sessionmaker()() as session:
            if await seed(session):
                log.info("demo_data_ready")
    from app.ai.runtime import ai_runtime

    await ai_runtime.start()
    log.info("startup", env=settings.environment, llm_provider=settings.llm_provider)
    yield
    await ai_runtime.stop()
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="1.0.0",
        description="Employee leave management: multi-level approvals, documents, audit "
        "trail and an AI assistant. Errors follow RFC 9457 (application/problem+json).",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )
    register_error_handlers(app)

    from app.api.routes import ai, extras

    api = APIRouter(prefix="/api/v1")
    for r in (auth.router, leaves.router, admin.router, ai.router, extras.router):
        api.include_router(r)
    app.include_router(api)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["ops"])
    async def ready() -> JSONResponse:
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            return JSONResponse({"status": "ready", "database": "ok"})
        except Exception as e:  # pragma: no cover
            log.warning("readiness_failed", error=str(e))
            return JSONResponse({"status": "unavailable", "database": "down"}, status_code=503)

    _mount_spa(app, settings.serve_frontend_dir)
    return app


def _mount_spa(app: FastAPI, directory: str | None) -> None:
    """Serve the built React app from the same origin (one image, one port, no CORS)."""
    if not directory or not Path(directory, "index.html").exists():
        return
    root = Path(directory).resolve()
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise StarletteHTTPException(404)
        candidate = (root / path).resolve()
        if path and root in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(root / "index.html")


app = create_app()
