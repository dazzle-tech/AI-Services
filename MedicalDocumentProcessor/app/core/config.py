"""Configuration management for the Medical Document Processor service."""
import json
from typing import Dict

from pydantic_settings import BaseSettings, SettingsConfigDict


# Default per-document-type relevance windows (in days). Deliberately configurable via
# env (RELEVANCE_WINDOWS_DAYS_JSON) rather than hardcoded in the pipeline logic, since
# these thresholds are expected to need tuning later (Step 2 of the pipeline).
DEFAULT_RELEVANCE_WINDOWS_DAYS: Dict[str, int] = {
    "lab_result": 180,
    "radiology_report": 365,
    "imaging_report": 365,
    "prescription": 90,
    "clinical_note": 365,
    "physician_note": 365,
    "discharge_summary": 365,
    "other": 365,
}


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8",
    )

    # API Configuration
    api_title: str = "Medical Document Processor Service"
    api_version: str = "1.0.0"
    api_description: str = (
        "Validation -> relevance -> translation -> structured formatting pipeline for "
        "uploaded medical documents, powered by OpenAI GPT."
    )
    api_host: str = "0.0.0.0"
    api_port: int = 8029
    api_reload: bool = False

    # OpenAI Configuration
    openai_api_key: str = ""
    openai_base_url: str | None = "http://localhost:11434/v1"
    openai_model: str = "gpt-4o"
    # Separate, optionally-overridable model for the vision OCR path (image documents).
    # Falls back to openai_model when unset, since gpt-4o is already vision-capable.
    openai_vision_model: str = ""
    openai_temperature: float = 0.1
    openai_max_tokens: int = 2000
    openai_timeout: int = 120
    openai_max_retries: int = 1
    openai_retry_delay: float = 1.0

    # Service Configuration
    max_input_length: int = 60000  # Extracted text truncated to this many chars in prompts
    max_upload_size_mb: int = 20
    enable_usage_tracking: bool = True
    default_target_language: str = "en"

    # OCR Configuration (image documents: JPG/PNG scanned docs)
    # "vision" (gpt-4o vision, default demo path) or "easyocr" (local, optional/guarded
    # import -- matches OCRParsingService's convention of keeping the heavy torch
    # dependency commented out of requirements.txt by default).
    ocr_engine: str = "vision"
    ocr_languages: str = "en"
    ocr_gpu: bool = False

    # Relevance Configuration (Step 2) -- JSON map of document_type -> max age in days.
    # Configurable, not hardcoded, so thresholds can be tuned without a code change.
    relevance_windows_days_json: str = json.dumps(DEFAULT_RELEVANCE_WINDOWS_DAYS)

    # Logging
    log_level: str = "INFO"

    @property
    def relevance_windows_days(self) -> Dict[str, int]:
        """Parsed per-document-type relevance windows, falling back to defaults on error."""
        try:
            parsed = json.loads(self.relevance_windows_days_json)
            if isinstance(parsed, dict):
                merged = dict(DEFAULT_RELEVANCE_WINDOWS_DAYS)
                merged.update({str(k): int(v) for k, v in parsed.items()})
                return merged
        except (ValueError, TypeError):
            pass
        return dict(DEFAULT_RELEVANCE_WINDOWS_DAYS)

    @property
    def ocr_languages_list(self) -> list[str]:
        languages = [lang.strip() for lang in self.ocr_languages.split(",") if lang.strip()]
        return languages or ["en"]

    @property
    def vision_model(self) -> str:
        return self.openai_vision_model or self.openai_model


settings = Settings()
