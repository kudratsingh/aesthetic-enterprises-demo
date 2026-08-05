from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.logging import RequestIDMiddleware, configure_logging
from app.routers import auth, health, hello, royalty


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(title="clinic-network-os", version="0.1.0")
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

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "detail": exc.detail},
        )

    return app


app = create_app()
