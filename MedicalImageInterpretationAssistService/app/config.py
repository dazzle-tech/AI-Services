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
    # Default to Ollama's OpenAI-compatible endpoint. Set OPENAI_BASE_URL=""
    # and provide a real OPENAI_API_KEY to switch back to the OpenAI cloud API.
    openai_base_url: str | None = "http://localhost:11434/v1"
    openai_api_key: str | None = "ollama"
    openai_model: str = ""
    enable_image_model: bool = True
    vision_model: str = Field(
        default="",
        validation_alias=AliasChoices("vision_model", "VISION_MODEL", "VISION_MODEL_NAME"),
    )
    # Ollama expects image_url as a flat data-URI string, while OpenAI/vLLM/LM Studio
    # expect the nested {"url": "...", "detail": "..."} object form.
    vision_image_url_as_string: bool = True
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
