"""Configuration management for ConvoScribe."""

from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Configuration
    api_title: str = "ConvoScribe"
    api_version: str = "1.0.0"
    api_description: str = (
        "AI-powered doctor-patient conversation summarization using OpenAI"
    )
    api_host: str = "0.0.0.0"
    api_port: int = 8026
    api_reload: bool = False
    api_key: str = "dev-api-key-change-me"
    log_level: str = "INFO"

    # OpenAI Configuration
    openai_api_key: str = ""
    openai_base_url: str | None = None
    role_id_model: str = "gpt-4o"
    summary_model: str = "gpt-4o"
    openai_temperature: float = 0.2
    openai_timeout: int = 120
    openai_max_retries: int = 1
    openai_retry_delay: float = 1.0
    enable_usage_tracking: bool = True
    use_llm_stub: bool = False

    # Database
    database_url: str = "postgresql://convoscribe:convoscribe@localhost:5432/convoscribe"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Object storage
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "convoscribe-audio"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False
    s3_server_side_encryption: str = ""  # AES256 for AWS S3; leave empty for MinIO

    # Transcription
    transcription_backend: str = "stub"
    whisper_model_size: str = "base"
    pyannote_hf_token: str = ""
    max_audio_duration_seconds: int = 3600
    allowed_audio_extensions: str = "wav,mp3,m4a"

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
