from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.database import init_db
from app.errors import register_exception_handlers
from app.logging_config import RequestLoggingMiddleware, configure_logging
from app.routers import projects_router, system_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Ensure storage and schema exist before serving any request.
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


def create_app() -> FastAPI:
    """Application factory: build and fully wire the FastAPI app."""
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        description=(
            "Phase 1 backend for deterministic construction estimating. "
            "All pricing arithmetic belongs in a separate Python pricing engine."
        ),
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(app)

    # Unversioned system probes (conventional for liveness/readiness tooling).
    app.include_router(system_router)
    # Versioned API surface.
    app.include_router(system_router, prefix=settings.api_v1_prefix)
    app.include_router(projects_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
