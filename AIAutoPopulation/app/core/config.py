"""Configuration management for the AI Auto-Population Service."""
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
    api_title: str = "AI Auto-Population Service"
    api_version: str = "1.0.0"
    api_description: str = "Healthcare AI service for clinical documentation auto-population"
    
    # OpenAI Configuration
    openai_api_key: str
    openai_base_url: Optional[str] = "http://localhost:11434/v1"
    openai_model: str = ""
    openai_temperature: float = 0.0  # Deterministic behavior
    openai_timeout: int = 120
    openai_max_retries: int = 1
    openai_max_tokens: int = 4000
    openai_max_tokens_vitals_only: int = 500  # Reduced tokens for faster vitals-only extraction (only vitals needed)
    
    # Service Configuration
    max_input_length: int = 10000  # Maximum characters in user input
    max_patient_data_size: int = 50000  # Maximum size for patient data dict
    
    # Server Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8010  # Server port (override with PORT env)
    api_reload: bool = True

    # Safety Configuration
    require_explicit_fields: bool = True
    strict_json_validation: bool = True
    use_backend_only_contradictions: bool = True  # If True, only use backend deterministic checks; if False, merge with AI contradictions
    completeness_audit_mode: bool = False  # If True, flag uncertainty for all fields; if False, only flag requested fields


settings = Settings()

