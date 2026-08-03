"""Configuration management for CodingAssist."""
import os
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, env_file_encoding="utf-8", extra="ignore"
    )

    # API Metadata
    api_title: str = "CodingAssist - AI Medical Coding & Charge-Capture Service"
    api_version: str = "1.0.0"
    api_description: str = (
        "Pipeline that ingests encounter documentation, normalizes and "
        "reconciles multiple source documents, extracts billable diagnoses "
        "and procedures, grounds them in ICD-10-CM/CPT/HCPCS via a local RAG "
        "store backed by the live NLM Clinical Tables API, runs deterministic "
        "NCCI/MUE/medical-necessity compliance checks, and drafts a "
        "structured, review-ready charge ticket."
    )

    # OpenAI Configuration
    openai_api_key: str
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_temperature: float = 0.2
    openai_timeout: int = 120
    openai_max_retries: int = 3
    openai_retry_delay: float = 1.0

    # NLM Clinical Tables (ICD-10-CM, HCPCS Level II) -- public, keyless API.
    # CPT (HCPCS Level I) has no free public lookup API; it is RAG/seed-only.
    clinical_tables_base_url: str = "https://clinicaltables.nlm.nih.gov/api"

    # Domain file paths (relative to project root)
    coding_edit_rules_file: str = "coding_edit_rules.json"
    medical_necessity_file: str = "medical_necessity_policies.json"
    billing_guide_file: str = "billing_data_guide.txt"
    output_schema_file: str = "output_schema.json"
    seed_terms_file: str = "coding_seed_terms.json"

    # RAG Configuration
    rag_persist_dir: str = "rag_db"
    rag_collection_name: str = "coding_ontology"
    rag_top_k: int = 3
    rag_similarity_threshold: float = 0.55

    # Server Configuration
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8025, validation_alias=AliasChoices("API_PORT", "PORT"))
    api_reload: bool = False

    # Project paths (resolved at import time)
    project_dir: str = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


settings = Settings()
