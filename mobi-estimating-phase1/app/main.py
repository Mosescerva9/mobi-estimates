from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth import ApiKeyAuthMiddleware
from app.config import settings
from app.database import init_db
from app.errors import register_exception_handlers
from app.extraction_db import upsert_trade_definition
from app.logging_config import RequestLoggingMiddleware, configure_logging
from app.routers import projects_router, system_router
from app.routers_boe import boe_router
from app.routers_coverage import coverage_router
from app.routers_processing import processing_router
from app.routers_qa import qa_router
from app.routers_extraction import extraction_router, trades_router
from app.routers_pricing import cost_books_router, pricing_router
from app.routers_pricing_prep import pricing_prep_router
from app.routers_proposals import proposals_router
from app.trades import bootstrap_trades
from app.trades.registry import trade_registry


def bootstrap() -> None:
    """Register configured trade modules and persist their definitions."""
    bootstrap_trades(settings.enabled_trades)
    for module in trade_registry.list_modules():
        definition = module.get_definition()
        upsert_trade_definition(
            trade_code=module.trade_code, trade_name=module.trade_name,
            module_version=module.module_version, schema_version=module.schema_version,
            enabled=True, metadata={"csi_divisions": definition.csi_divisions},
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Ensure storage and schema exist before serving any request.
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db()
    bootstrap()
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

    # API-key gate runs inside the logging middleware (added first, so it is the
    # inner layer) so rejected requests still get a request id and access-log
    # line. No-op when MOBI_API_KEY is unset.
    app.add_middleware(ApiKeyAuthMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(app)

    # Unversioned system probes (conventional for liveness/readiness tooling).
    app.include_router(system_router)
    # Versioned API surface.
    app.include_router(system_router, prefix=settings.api_v1_prefix)
    app.include_router(projects_router, prefix=settings.api_v1_prefix)
    app.include_router(processing_router, prefix=settings.api_v1_prefix)
    app.include_router(trades_router, prefix=settings.api_v1_prefix)
    app.include_router(extraction_router, prefix=settings.api_v1_prefix)
    app.include_router(boe_router, prefix=settings.api_v1_prefix)
    app.include_router(coverage_router, prefix=settings.api_v1_prefix)
    app.include_router(qa_router, prefix=settings.api_v1_prefix)
    app.include_router(cost_books_router, prefix=settings.api_v1_prefix)
    app.include_router(pricing_prep_router, prefix=settings.api_v1_prefix)
    app.include_router(pricing_router, prefix=settings.api_v1_prefix)
    app.include_router(proposals_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
