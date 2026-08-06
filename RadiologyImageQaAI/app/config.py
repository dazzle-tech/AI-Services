from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "radiology-qc-ai"
    api_v1_prefix: str = "/api/v1"
    api_host: str = "0.0.0.0"
    api_port: int = 8016
    api_reload: bool = False
    log_level: str = "INFO"

    # Safety / regulatory controls
    disclaimer_text: str = (
        "Research/MVP only. Not for clinical use without validation and regulatory approval."
    )

    # QC behavior controls
    bladder_missing_is_fail: bool = False

    # File handling
    max_upload_mb: int = 2048

    # Optional OpenAI report generation (never required for QC logic)
    openai_enabled: bool = False
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    openai_timeout: float = 120.0
    openai_max_retries: int = 1
    deidentify_before_gpt: bool = True
    openai_report_style_default: Literal["technologist_alert", "short", "verbose"] = "technologist_alert"


@lru_cache
def get_settings() -> Settings:
    return Settings()
