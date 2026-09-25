"""FastAPI application factory.

Run with:  uvicorn app.main:create_app --factory --reload
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import evals, projects, sessions
from app.config import Settings, get_settings
from app.db.database import Database
from app.llm.base import LLMProvider
from app.llm.factory import create_provider
from app.logging_config import configure_logging
from app.services.errors import ConflictError, NotFoundError
from app.services.session_service import SessionService


def create_app(
    settings: Settings | None = None,
    provider_factory: Callable[[], LLMProvider] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    database = Database(settings.database_url)
    database.create_tables()
    service = SessionService(settings, database, provider_factory or (lambda: create_provider(settings)))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        service.wait_for_idle()

    app = FastAPI(title="CodePilot", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_service = service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(NotFoundError)
    async def not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok", "provider": settings.llm_provider}

    for router in (projects.router, sessions.router, evals.router):
        app.include_router(router, prefix="/api")
    return app
