"""Configuration management for the Nurse Task Prioritization Service."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8"
    )

    # API Configuration
    api_title: str = "Nurse Task Prioritization Service"
    api_version: str = "1.0.0"
    api_description: str = "AI-powered nursing task prioritization using OpenAI"

    # OpenAI Configuration
    openai_api_key: str
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o"
    openai_temperature: float = 0.2
    openai_max_tokens: int = 2000

    # API Configuration
    openai_timeout: int = 120
    openai_max_retries: int = 1
    openai_retry_delay: float = 1.0

    # Service Configuration
    max_input_length: int = 50000
    enable_usage_tracking: bool = True

    # Server Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8002
    api_reload: bool = False

    # Logging
    log_level: str = "INFO"


settings = Settings()
