from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.logging import RequestIDMiddleware, configure_logging
from app.db.engine import connected_role_bypasses_rls
from app.routers import (
    auth,
    health,
    hello,
    ingest,
    kpi,
    locations,
    portal,
    royalty,
    supply,
    variance,
)

logger = structlog.get_logger()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup guard: tenancy lives in RLS (ADR-0002), so a DB role that skips
    RLS (SUPERUSER or BYPASSRLS — e.g. Neon's database owner) means every
    tenant sees everything. Refuse to serve in prod; warn loudly elsewhere."""
    settings = get_settings()
    try:
        bypasses = await connected_role_bypasses_rls()
    except OperationalError:
        bypasses = None
        logger.warning("rls_guard_skipped", reason="database unreachable at startup")
    if bypasses:
        if settings.environment == "prod":
            raise RuntimeError(
                "refusing to start: the app's database role can bypass RLS "
                "(SUPERUSER/BYPASSRLS). Connect as a non-privileged role — "
                "see ADR-0002 and docs/runbooks/deploy.md."
            )
        logger.warning(
            "rls_not_enforceable",
            reason="app database role has SUPERUSER or BYPASSRLS",
            environment=settings.environment,
        )
    yield


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(title="clinic-network-os", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(hello.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(royalty.router, prefix="/api/v1")
    app.include_router(kpi.router, prefix="/api/v1")
    app.include_router(variance.router, prefix="/api/v1")
    app.include_router(supply.router, prefix="/api/v1")
    app.include_router(ingest.router, prefix="/api/v1")
    app.include_router(locations.router, prefix="/api/v1")
    app.include_router(portal.router, prefix="/api/v1")

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "detail": exc.detail},
        )

    return app


app = create_app()
