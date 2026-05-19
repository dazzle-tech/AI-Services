from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "medical-image-interpretation-assist"
    api_v1_prefix: str = "/api/v1"
    disclaimer_text: str = "Assistive AI only. Radiologist review required. Not for final diagnosis."

    max_upload_mb: int = 2048
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-2024-11-20"
    openai_timeout_seconds: float = 30.0
    ct_max_slices: int = 6
    audit_log_dir: str = "/var/log/miias"


@lru_cache
def get_settings() -> Settings:
    return Settings()
