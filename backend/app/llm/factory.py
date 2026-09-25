"""Builds the configured LLM provider. The only place that knows which providers exist."""

from app.config import Settings
from app.llm.base import LLMProvider


def create_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        api_key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        return AnthropicProvider(api_key=api_key, model=settings.anthropic_model, effort=settings.anthropic_effort)
    if settings.llm_provider == "ollama":
        from app.llm.ollama_provider import OllamaProvider

        return OllamaProvider(model=settings.ollama_model, base_url=settings.ollama_base_url, num_ctx=settings.ollama_num_ctx)
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider!r} (expected 'anthropic' or 'ollama')")
