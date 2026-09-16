"""Configuration for the NurseHandOver service.

Reads the SHARED OpenAI-compatible endpoint vars used by every service in this repo
(OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL), so the whole stack points at one
endpoint via the root .env — see `x-llm-env` in docker-compose.yml.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Shared LLM endpoint (OpenAI-compatible)
    openai_api_key: str = ""
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o"

    # Generation parameters
    temperature: float = 0.2
    max_retries: int = 2

    # HTTP
    port: int = 8028


settings = Settings()
