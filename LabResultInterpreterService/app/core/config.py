"""Configuration management for the Lab Result Interpreter Service."""
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
    api_title: str = "Lab Result Interpreter Service"
    api_version: str = "1.0.0"
    api_description: str = "AI-powered lab result interpretation support using OpenAI"

    # OpenAI Configuration
    openai_api_key: str
    openai_base_url: str | None = "http://localhost:11434/v1"
    openai_model: str = ""
    openai_temperature: float = 0.2
    openai_max_tokens: int = 1500  # Lab interpretation responses are longer

    # API Configuration
    openai_timeout: int = 120
    openai_max_retries: int = 1
    openai_retry_delay: float = 1.0

    # Service Configuration
    max_input_length: int = 50000  # Labs + historical can be large
    enable_usage_tracking: bool = True

    # Server Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8003
    api_reload: bool = False

    # Logging
    log_level: str = "INFO"


settings = Settings()
