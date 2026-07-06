"""Configuration management for SepsisSentinel."""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8"
    )

    # API Metadata
    api_title: str = "SepsisSentinel - Clinical AI Sepsis Detection"
    api_version: str = "1.0.0"
    api_description: str = (
        "REST API for AI-powered sepsis early detection using GPT-4o. "
        "Analyses 24-hour patient time-series data and returns a "
        "comprehensive sepsis risk assessment."
    )

    # OpenAI Configuration
    openai_api_key: str
    openai_base_url: str | None = "http://localhost:11434/v1"
    openai_model: str = ""
    openai_temperature: float = 0.2
    openai_timeout: int = 120
    openai_max_retries: int = 1
    openai_retry_delay: float = 1.0

    # Server Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8023
    api_reload: bool = False

    # Project paths (resolved at import time)
    project_dir: str = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


settings = Settings()
