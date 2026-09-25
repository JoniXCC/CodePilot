"""FastAPI dependencies. Route handlers ask for what they need via Depends(...)
instead of creating it, so tests can build the app with fakes (e.g. a scripted LLM)."""

from fastapi import Request

from app.config import Settings
from app.services.session_service import SessionService


def get_service(request: Request) -> SessionService:
    return request.app.state.session_service


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings
