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

    # Speech: OpenAI Realtime gpt-live-transcribe. USE_LLM_STUB=true replaces it with a scripted transcriber.
    live_transcribe_model: str = "gpt-live-transcribe"
    live_transcribe_delay: str = "low"  # minimal | low | medium | high | xhigh — low balances speed and accuracy
    live_transcribe_char_ms: float = 0  # unused; partials send each real model delta once
    live_transcribe_prompt: str = (
        "Doctor-patient clinic visit in English or Arabic only. "
        "Transcribe exactly what was spoken. "
        "Write all numbers as digits, never as words "
        "(2 not two, 4 out of 10 not four out of ten, "
        "36.7 not thirty-six point seven, "
        "128/82 not one hundred twenty-eight over eighty-two, "
        "5 mg not five milligram). "
        "Keep medical wording exact: Good morning, blood pressure, headache, "
        "amlodipine, nausea, vomiting, fever, dehydration, arrange a review. "
        "Do not invent or swap words."
    )
    live_transcribe_keywords: str = (
        "Good morning,Dr. Patel,Sarah Johnson,headache,blood pressure,amlodipine,"
        "nausea,vomiting,fever,dehydration,arrange a review"
    )
    # Kept for older env files and the unused faster-whisper helper module.
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = ""
    whisper_language: str = ""
    whisper_model_cache: str = ""

    # Live segmenting
    stream_chunk_seconds: float = 4.0  # a partial line is refreshed this often while someone talks
    stream_overlap_seconds: float = 0.5  # audio carried into the next line when a long line is split
    silence_ms: int = 800  # this much silence ends a line (it becomes final)
    silence_rms: float = 0.01  # frame energy below this is silence (0-1 float scale)
    min_speech_ms: int = 250  # shorter bursts are noise and are dropped
    max_turn_seconds: float = 30.0  # a line is split here even without silence
    max_backlog_seconds: float = 2.0  # when this far behind real time, partial lines are skipped

    # How many visits this process will hold at once, and how long one visit may run.
    max_sessions: int = 8
    max_session_seconds: float = 3600
    session_warn_seconds: float = 2700  # one warning, then the visit continues until max_session_seconds
    start_timeout_seconds: float = 10  # close if `start` never arrives
    idle_timeout_seconds: float = 30  # no audio while the visit is running
    pause_timeout_seconds: float = 900  # close a visit left on pause
    max_frame_bytes: int = 524288
    max_backlog_hard_seconds: float = 30  # past this, refuse the visit; the soft backlog only skips partials

    # Language hints for gpt-live-transcribe (comma-separated). Also used by the unused Whisper helper.
    whisper_languages: str = "ar,en"
    whisper_initial_prompt: str = ""  # used when LIVE_TRANSCRIBE_PROMPT is blank
    whisper_no_speech_threshold: float = 0.6
    whisper_min_avg_logprob: float = -1.0
    whisper_max_compression_ratio: float = 2.4
    whisper_word_confidence: bool = False
    whisper_low_confidence: float = 0.6

    # "Picked up so far"
    # Kept for older .env files; extract no longer waits on this (display-only, send after every final).
    picked_up_interval_seconds: float = 0.0
    picked_up_max_interval_seconds: float = 0.0
    extract_max_concurrency: int = 4
    stop_flush_timeout_seconds: float = 45  # on stop, wait for the last list update, then send `final` anyway
    live_extract_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_temperature: float = 0.0
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 2
    use_llm_stub: bool = False

    # /try, /docs, /redoc and /openapi.json. Off unless a deployment explicitly turns them on.
    enable_dev_pages: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()] or ["*"]

    @property
    def whisper_language_list(self) -> list[str]:
        return [item.strip() for item in self.whisper_languages.split(",") if item.strip()]


settings = Settings()


def get_settings() -> Settings:
    return settings


def reload_settings() -> Settings:
    global settings
    new_settings = Settings()
    for name in Settings.model_fields:
        object.__setattr__(settings, name, getattr(new_settings, name))
    return settings
