"""gpt-live-transcribe helpers (no live OpenAI call)."""

from types import SimpleNamespace

import numpy as np

from app.asr.live_transcribe import (
    _float32_to_b64_pcm16,
    _realtime_url,
    _session_config,
    _to_live_pcm,
)
from app.audio.pcm import TARGET_SR


def test_realtime_url_defaults_to_openai_transcription():
    assert _realtime_url("") == "wss://api.openai.com/v1/realtime?intent=transcription"
    assert _realtime_url("https://api.openai.com/v1") == "wss://api.openai.com/v1/realtime?intent=transcription"
    assert _realtime_url("https://example.com") == "wss://example.com/v1/realtime?intent=transcription"


def test_session_config_includes_model_languages_and_delay():
    settings = SimpleNamespace(
        live_transcribe_model="gpt-live-transcribe",
        live_transcribe_delay="minimal",
        live_transcribe_prompt="A clinic visit.",
        live_transcribe_keywords="amlodipine, Sarah",
        whisper_initial_prompt="",
        whisper_language_list=["ar", "en"],
    )
    config = _session_config(settings)
    transcription = config["audio"]["input"]["transcription"]
    assert transcription["model"] == "gpt-live-transcribe"
    assert transcription["delay"] == "minimal"
    assert transcription["prompt"] == "A clinic visit."
    assert transcription["languages"] == ["ar", "en"]
    assert transcription["keywords"] == ["amlodipine", "Sarah"]
    assert config["audio"]["input"]["turn_detection"] is None


def test_audio_is_resampled_to_24k_pcm():
    one_second = np.zeros(TARGET_SR, dtype=np.float32)
    live = _to_live_pcm(one_second)
    assert live.shape[0] == 24_000
    encoded = _float32_to_b64_pcm16(live)
    assert isinstance(encoded, str) and len(encoded) > 0
