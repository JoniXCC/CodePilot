"""Application settings, loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    llm_provider: str = "anthropic"
    # SecretStr keeps the key out of repr()/logs by accident.
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5"

    projects_dir: Path = Path("../examples")
    database_url: str = "sqlite:///./codepilot.db"

    agent_max_steps: int = 25
    command_timeout_seconds: int = 120

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
