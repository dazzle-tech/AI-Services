"""Configuration management for Medical Imaging Assist."""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


DISCLAIMER_TEXT = (
    "This output is for assistive purposes only and is not a final diagnosis. "
    "Review by a board-certified radiologist is required."
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, env_file_encoding="utf-8", extra="ignore"
    )

    # API Metadata
    api_title: str = "Medical Imaging Assist - Radiologist Assistive AI"
    api_version: str = "1.0.0"
    api_description: str = (
        "FastAPI service that validates DICOM metadata, corrects radiology reports, "
        "and reconciles AI image analysis with clinical documentation. "
        "All output is assistive only and requires board-certified radiologist review."
    )

    # OpenAI Configuration
    # Keep this optional so the service can start (e.g. to serve /health and
    # non-AI endpoints) even when an API key is not configured. AI endpoints
    # will still fail with a clear error when invoked.
    openai_base_url: str = "http://localhost:11434/v1"
    openai_api_key: str = "ollama"
    openai_model: str = ""
    openai_temperature: float = 0.2
    openai_timeout: int = 120
    openai_max_retries: int = 1
    openai_retry_delay: float = 1.0
    openai_embed_model: str = "nomic-embed-text"

    # RAG / domain data files (relative to project root)
    icd10_file: str = "rag_data/icd10cm.json"
    radlex_file: str = "rag_data/radlex.json"
    rag_embeddings_file: str = "rag_data/embeddings.npz"
    terms_guide_file: str = "medical_terms_guide.txt"
    output_schema_file: str = "output_schema.json"

    # Server Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8024
    api_reload: bool = False

    # Output persistence
    persist_output: bool = True

    # Project paths (resolved at import time)
    project_dir: str = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


settings = Settings()
