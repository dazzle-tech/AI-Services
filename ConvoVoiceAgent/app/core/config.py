"""Configuration for ConvoVoiceAgent."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    api_title: str = "ConvoVoiceAgent"
    api_version: str = "1.0.0"
    api_description: str = (
        "One call for a clinical visit recording. Audio goes to ConvoScribe, "
        "the clinical JSON goes to SystemDisplayPlugin, and that view JSON is the response."
    )
    api_host: str = "0.0.0.0"
    api_port: int = 8036
    api_reload: bool = False
    log_level: str = "INFO"

    convoscribe_base_url: str = "http://localhost:8026"
    system_display_base_url: str = "http://localhost:8031"
    http_timeout_seconds: float = 180.0
    default_view_ids: str = "soap_note"
    default_context_type: str = "appointment"
    default_purpose: str = "soap_note"
    default_detail_level: str = "standard"

    ambient_note_model: str = "gpt-4o"
    use_llm_stub: bool = False
    openai_api_key: str = ""
    openai_base_url: str | None = None
    openai_temperature: float = 0.1
    openai_timeout_seconds: float = 120.0
    ambient_low_confidence_threshold: float = 0.6

    @property
    def default_view_id_list(self) -> list[str]:
        return [item.strip() for item in self.default_view_ids.split(",") if item.strip()] or ["soap_note"]


settings = Settings()


def get_settings() -> Settings:
    return settings


def reload_settings() -> Settings:
    global settings
    new_settings = Settings()
    for name in Settings.model_fields:
        object.__setattr__(settings, name, getattr(new_settings, name))
    return settings
