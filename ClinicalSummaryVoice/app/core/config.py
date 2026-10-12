"""Configuration for ClinicalSummaryVoice."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    api_title: str = "ClinicalSummaryVoice"
    api_version: str = "1.0.0"
    api_description: str = (
        "One speaker dictates a clinical summary. The service transcribes the audio "
        "and returns a structured summary. It does not identify multiple speakers."
    )
    api_host: str = "0.0.0.0"
    api_port: int = 8037
    api_reload: bool = False
    log_level: str = "INFO"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_summary_model: str = "gpt-4o"
    openai_transcribe_model: str = "gpt-4o-transcribe"
    openai_temperature: float = 0.1
    openai_timeout: float = 120.0
    openai_max_retries: int = 1
    use_llm_stub: bool = False


settings = Settings()


def reload_settings() -> Settings:
    global settings
    new_settings = Settings()
    for name in Settings.model_fields:
        object.__setattr__(settings, name, getattr(new_settings, name))
    return settings
