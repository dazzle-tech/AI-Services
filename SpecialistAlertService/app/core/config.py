"""Configuration management for the Specialist Alert Service."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8",
    )

    api_title: str = "Specialist Alert Service"
    api_version: str = "1.1.0"
    api_description: str = (
        "REST API-first clinical alert and specialty consultation decision support service using OpenAI"
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_temperature: float = 0.1
    openai_max_tokens: int = 1400

    openai_timeout: int = 45
    openai_max_retries: int = 3
    openai_retry_delay: float = 1.0

    max_input_length: int = 50000
    enable_usage_tracking: bool = True

    api_host: str = "0.0.0.0"
    api_port: int = 8014
    api_reload: bool = False
    log_level: str = "INFO"


settings = Settings()
