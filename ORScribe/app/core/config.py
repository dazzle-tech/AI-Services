"""Configuration management for ORScribe."""

from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_FILE, override=True)


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Configuration
    api_title: str = "ORScribe"
    api_version: str = "1.0.0"
    api_description: str = (
        "AI-powered operating room conversation intelligence using OpenAI"
    )
    api_host: str = "0.0.0.0"
    api_port: int = 8030
    api_reload: bool = False
    api_key: str = "dev-api-key-change-me"
    log_level: str = "INFO"

    # OpenAI Configuration
    openai_api_key: str = ""
    openai_base_url: str | None = None
    role_id_model: str = "gpt-4o"
    record_model: str = "gpt-4o"
    openai_temperature: float = 0.2
    openai_timeout: int = 120
    openai_max_retries: int = 1
    openai_retry_delay: float = 1.0
    enable_usage_tracking: bool = True
    use_llm_stub: bool = False
    role_confidence_threshold: str = "medium"

    # Database (5434 = docker-compose host port)
    database_url: str = "postgresql://orscribe:orscribe@localhost:5434/orscribe"

    # Celery (optional background workers; not required for POST /analyze)
    celery_broker_url: str = "redis://localhost:6381/0"
    celery_result_backend: str = "redis://localhost:6381/1"

    # Object storage (9002 = docker-compose MinIO host port)
    s3_endpoint: str = "http://localhost:9002"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "orscribe-audio"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False
    s3_server_side_encryption: str = "AES256"

    # Transcription
    transcription_backend: str = "stub"
    whisper_model_size: str = "base"
    openai_transcribe_model: str = "gpt-4o-transcribe"
    pyannote_hf_token: str = ""
    max_audio_duration_seconds: int = 14400
    allowed_audio_extensions: str = "wav,mp3,m4a"
    chunk_duration_seconds: int = 600

    # Retention
    audio_retention_days: int = 30

    @field_validator("allowed_audio_extensions", mode="before")
    @classmethod
    def _normalize_extensions(cls, value: str) -> str:
        return value.lower().strip()

    @property
    def allowed_extensions_list(self) -> List[str]:
        return [ext.strip() for ext in self.allowed_audio_extensions.split(",") if ext.strip()]


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
