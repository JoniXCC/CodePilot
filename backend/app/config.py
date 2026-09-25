"""Application settings, loaded from environment variables (and an optional .env file)."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The project root (the folder containing backend/, frontend/, examples/ ...).
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "anthropic"
    # SecretStr keeps the key out of repr()/logs by accident.
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5"
    anthropic_effort: str = "high"  # low | medium | high | xhigh | max

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_num_ctx: int = 16_384

    # Relative paths are resolved from the project root, whatever the current directory is.
    projects_dir: Path = REPO_ROOT / "demo-projects"
    database_url: str = f"sqlite:///{(REPO_ROOT / 'codepilot.db').as_posix()}"

    agent_max_steps: int = 25
    command_timeout_seconds: int = 120

    log_level: str = "INFO"

    @property
    def model_name(self) -> str:
        """The model the configured provider will use (shown in sessions and eval reports)."""
        return {"anthropic": self.anthropic_model, "ollama": self.ollama_model}.get(self.llm_provider, self.llm_provider)

    @field_validator("projects_dir")
    @classmethod
    def _resolve_projects_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
