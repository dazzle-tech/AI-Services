from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

    service_name: str = "medical-image-interpretation-assist"
    api_v1_prefix: str = "/api/v1"
    api_host: str = "0.0.0.0"
    api_port: int = 8015
    api_reload: bool = False
    log_level: str = "INFO"
    disclaimer_text: str = "Assistive AI only. Radiologist review required. Not for final diagnosis."

    max_upload_mb: int = 2048
    # Leave OPENAI_BASE_URL empty to use the OpenAI cloud API.
    # Set OPENAI_BASE_URL to an OpenAI-compatible endpoint (e.g. Ollama) to override.
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    enable_image_model: bool = True
    vision_model: str = Field(
        default="gpt-4o",
        validation_alias=AliasChoices("vision_model", "VISION_MODEL", "VISION_MODEL_NAME"),
    )
    # OpenAI expects the nested {"url": "...", "detail": "..."} object form.
    # Set true for Ollama-style flat data-URI strings.
    vision_image_url_as_string: bool = False
    openai_timeout: float = 120.0
    openai_max_retries: int = 1
    ct_max_slices: int = 6
    audit_log_dir: str = "/var/log/miias"

    @property
    def image_input_enabled(self) -> bool:
        return self.enable_image_model and bool(self.vision_model.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
