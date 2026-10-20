"""Configuration for LiveVisitScribe."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_title: str = "LiveVisitScribe"
    api_version: str = "1.0.0"
    api_description: str = (
        "Live transcript for a clinical visit. The browser streams microphone audio over a WebSocket "
        "and gets labelled lines plus a 'picked up so far' list. Nothing is stored; every message is "
        "provisional and is not the chart note."
    )
    host: str = "0.0.0.0"
    port: int = 8037
    log_level: str = "INFO"
    cors_origins: str = "*"

    # Speech (faster-whisper). USE_LLM_STUB=true replaces it with a scripted transcriber.
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = ""
    whisper_language: str = ""  # blank = auto-detect (Arabic and English are both expected)
    whisper_model_cache: str = ""

    # Live segmenting
    stream_chunk_seconds: float = 4.0  # a partial line is refreshed this often while someone talks
    stream_overlap_seconds: float = 0.5  # audio carried into the next line when a long line is split
    silence_ms: int = 800  # this much silence ends a line (it becomes final)
    silence_rms: float = 0.01  # frame energy below this is silence (0-1 float scale)
    min_speech_ms: int = 250  # shorter bursts are noise and are dropped
    max_turn_seconds: float = 30.0  # a line is split here even without silence
    max_backlog_seconds: float = 2.0  # when this far behind real time, partial lines are skipped

    # "Picked up so far"
    picked_up_interval_seconds: float = 8.0
    live_extract_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_temperature: float = 0.0
    openai_timeout_seconds: float = 30.0
    use_llm_stub: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()] or ["*"]


settings = Settings()


def get_settings() -> Settings:
    return settings


def reload_settings() -> Settings:
    global settings
    new_settings = Settings()
    for name in Settings.model_fields:
        object.__setattr__(settings, name, getattr(new_settings, name))
    return settings
