"""Configuration management for ORDisplayPlugin."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # API Configuration
    api_title: str = "ORDisplayPlugin"
    api_version: str = "1.0.0"
    api_description: str = (
        "Stage-2 field mapper: reshapes ORScribe JSON (timeline, checklist, "
        "medications, roles) onto target OR views without regenerating clinical content"
    )
    api_host: str = "0.0.0.0"
    api_port: int = 8032
    api_reload: bool = False
    log_level: str = "INFO"

    # OpenAI Configuration
    openai_api_key: str = ""
    openai_base_url: str | None = None
    # OPENAI_MODEL is the env name used by sibling services; accept it as an alias.
    mapping_model: str = Field(
        default="gpt-4o",
        validation_alias=AliasChoices("MAPPING_MODEL", "OPENAI_MODEL", "mapping_model", "openai_model"),
    )
    openai_temperature: float = 0.2
    openai_max_tokens: int = 2048
    openai_timeout: int = 120
    openai_max_retries: int = 1
    openai_retry_delay: float = 1.0
    enable_usage_tracking: bool = True
    use_llm_stub: bool = False

    # Database (5436 = docker-compose host port)
    database_url: str = (
        "postgresql://ordisplay:ordisplay@localhost:5436/ordisplay"
    )


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
