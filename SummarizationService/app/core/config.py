"""Configuration management for the Clinical Summary Service."""
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
    api_title: str = "Clinical Summary Service"
    api_version: str = "1.2.0"
    api_description: str = "AI-powered clinical summary generation using OpenAI"
    
    # OpenAI Configuration
    openai_api_key: str
    openai_base_url: str | None = "http://localhost:11434/v1"
    openai_model: str = ""
    openai_temperature: float = 0.2  # Low temperature for consistent, factual summaries
    openai_max_tokens: int = 1200  # Headroom for reasoning-model overhead (see /no_think in prompts.py); summaries themselves are typically 100-300 tokens
    
    # API Configuration
    openai_timeout: int = 120  # Timeout for OpenAI API calls (seconds)
    openai_max_retries: int = 1  # Number of retries for transient failures
    openai_retry_delay: float = 1.0  # Delay between retries (seconds)
    
    # Service Configuration
    max_input_length: int = 10000  # Maximum characters in patient data
    enable_usage_tracking: bool = True  # Track token usage for cost monitoring
    
    # Server Configuration
    api_host: str = "0.0.0.0"  # Server host
    api_port: int = 8009  # Server port
    api_reload: bool = False  # Auto-reload on code changes (development)


settings = Settings()

