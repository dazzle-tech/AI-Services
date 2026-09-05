"""Unit tests for transcription backend selection."""

from unittest.mock import MagicMock, patch

from app.transcription import get_transcription_service
from app.transcription.openai_transcribe import OpenAITranscribeService
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


def test_factory_returns_openai_transcribe():
    with patch("app.transcription.settings.transcription_backend", "openai"):
        with patch.object(OpenAITranscribeService, "__init__", lambda self: None):
            assert isinstance(get_transcription_service(), OpenAITranscribeService)


def test_factory_accepts_gpt4o_transcribe_alias():
    with patch("app.transcription.settings.transcription_backend", "gpt-4o-transcribe"):
        with patch.object(OpenAITranscribeService, "__init__", lambda self: None):
            assert isinstance(get_transcription_service(), OpenAITranscribeService)


def test_openai_transcribe_returns_single_segment():
    service = OpenAITranscribeService.__new__(OpenAITranscribeService)
    service._model = "gpt-4o-transcribe"
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = MagicMock(text="Mental state normal.")
    service._client = mock_client

    segments = service.transcribe_and_diarize(b"RIFF", "clip.wav", time_offset=1.5)
    assert len(segments) == 1
    assert segments[0].text == "Mental state normal."
    assert segments[0].speaker_label == "SPEAKER_00"
    assert segments[0].start_time == 1.5
    mock_client.audio.transcriptions.create.assert_called_once()
    kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-4o-transcribe"
    assert kwargs["language"] == "en"
