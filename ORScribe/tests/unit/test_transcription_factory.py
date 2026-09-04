"""Unit tests for transcription backend selection."""

from unittest.mock import patch

from app.transcription import get_transcription_service
from app.transcription.stub import StubTranscriptionService
from app.transcription.whisper_only import WhisperOnlyTranscriptionService


def test_factory_returns_stub_by_default_name():
    with patch("app.transcription.settings.transcription_backend", "stub"):
        assert isinstance(get_transcription_service(), StubTranscriptionService)


def test_factory_returns_whisper_for_whisper_backend():
    with patch("app.transcription.settings.transcription_backend", "whisper"):
        with patch.object(WhisperOnlyTranscriptionService, "__init__", lambda self: None):
            assert isinstance(get_transcription_service(), WhisperOnlyTranscriptionService)


def test_factory_accepts_whisper_only_alias():
    with patch("app.transcription.settings.transcription_backend", "whisper_only"):
        with patch.object(WhisperOnlyTranscriptionService, "__init__", lambda self: None):
            assert isinstance(get_transcription_service(), WhisperOnlyTranscriptionService)
