"""Configuration management for SystemDisplayPlugin."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8",
    )

    # API Configuration
    api_title: str = "SystemDisplayPlugin"
    api_version: str = "1.0.0"
    api_description: str = (
        "Stage-2 field mapper: reshapes ORScribe/ConvoScribe JSON to a target view "
        "without regenerating clinical content"
    )
    api_host: str = "0.0.0.0"
    api_port: int = 8031
    api_reload: bool = False
    api_key: str = "dev-api-key-change-me"
    log_level: str = "INFO"

    # OpenAI Configuration
    openai_api_key: str = ""
    openai_base_url: str | None = None
    mapping_model: str = "gpt-4o"
    openai_temperature: float = 0.2
    openai_max_tokens: int = 2048
    openai_timeout: int = 120
    openai_max_retries: int = 1
    openai_retry_delay: float = 1.0
    enable_usage_tracking: bool = True
    use_llm_stub: bool = False

    # Database (5435 = docker-compose host port)
    # Assumption: reuse ORScribe/ConvoScribe SQLAlchemy+Postgres persistence for stored
    # ViewDecoders (same as CaseRecord/SessionRecord), not Redis/in-memory.
    database_url: str = (
        "postgresql://systemdisplay:systemdisplay@localhost:5435/systemdisplay"
    )

    # Redis — used only for health-check parity with ORScribe/ConvoScribe.
    # This service has no Celery workers (no audio ingest / async pipeline).
    redis_url: str = "redis://localhost:6382/0"


settings = Settings()


def get_settings() -> Settings:
    return settings


def reload_settings() -> Settings:
    """Reload settings from environment — mutates singleton for test compatibility."""
    global settings
    new_settings = Settings()
    for name in Settings.model_fields:
        object.__setattr__(settings, name, getattr(new_settings, name))
    return settings
