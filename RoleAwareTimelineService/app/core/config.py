"""Configuration for the Role-Aware Timeline Service."""
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVICE_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=_SERVICE_ROOT / ".env",
        case_sensitive=False,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_title: str = "Role-Aware Timeline Service"
    api_version: str = "1.0.0"
    api_description: str = (
        "Builds one shared clinical timeline and summary, then role-specific highlights, using OpenAI."
    )

    openai_api_key: str
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str
    openai_temperature: float = 0.0

    openai_timeout: int = 120
    openai_max_retries: int = 2
    openai_retry_delay: float = 1.0

    max_input_length: int = 200000
    enable_usage_tracking: bool = True
    log_level: str = "INFO"

    api_host: str = "0.0.0.0"
    api_port: int = 8040
    api_reload: bool = False

    @field_validator("openai_api_key", "openai_model", "openai_base_url")
    @classmethod
    def require_non_empty(cls, value: str, info) -> str:
        """Reject blank credentials, model names, and base URLs."""
        if not value or not str(value).strip():
            raise ValueError(f"{info.field_name} must be set")
        return str(value).strip()


settings = Settings()
