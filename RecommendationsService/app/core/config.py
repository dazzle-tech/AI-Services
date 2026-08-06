"""Configuration management for the Recommendations Service."""
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
    api_title: str = "Clinical Recommendations Service"
    api_version: str = "1.0.0"
    api_description: str = "AI-powered clinical recommendations using OpenAI"
    
    # OpenAI Configuration
    openai_api_key: str
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o"
    openai_temperature: float = 0.3  # Slightly higher for more nuanced recommendations
    openai_max_tokens: int = 1500  # Recommendations may be longer
    
    # API Configuration
    openai_timeout: int = 120
    openai_max_retries: int = 1
    openai_retry_delay: float = 1.0
    
    # Service Configuration
    max_input_length: int = 10000
    enable_usage_tracking: bool = True
    
    # Server Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8007
    api_reload: bool = False


settings = Settings()

