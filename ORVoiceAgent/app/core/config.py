"""Configuration for ORVoiceAgent."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    api_title: str = "ORVoiceAgent"
    api_version: str = "1.0.0"
    api_description: str = (
        "Same eight window paths as ORDisplayPlugin. Voice in, STT via ORScribe, "
        "then the matching DisplayPlugin endpoint; that JSON is the response."
    )
    api_host: str = "0.0.0.0"
    api_port: int = 8035
    api_reload: bool = False
    api_key: str = "dev-api-key-change-me"
    log_level: str = "INFO"

    orscribe_base_url: str = "http://localhost:8030"
    ordisplay_base_url: str = Field(
        default="http://localhost:8032",
        validation_alias=AliasChoices(
            "ORDISPLAY_BASE_URL", "OCR_PARSING_BASE_URL", "ordisplay_base_url"
        ),
    )
    orscribe_api_key: str = "dev-api-key-change-me"
    http_timeout_seconds: float = 60.0


settings = Settings()


def get_settings() -> Settings:
    return settings


def reload_settings() -> Settings:
    global settings
    new_settings = Settings()
    for name in Settings.model_fields:
        object.__setattr__(settings, name, getattr(new_settings, name))
    return settings
