"""Transcription backend factory."""

from app.core.config import settings
from app.transcription.base import TranscriptionService
from app.transcription.openai_transcribe import OpenAITranscribeService
from app.transcription.stub import StubTranscriptionService
from app.transcription.whisper_only import WhisperOnlyTranscriptionService
from app.transcription.whisper_pyannote import WhisperPyannoteTranscriptionService


def get_transcription_service() -> TranscriptionService:
    backend = settings.transcription_backend.lower()
    if backend in {"openai", "openai_transcribe", "gpt-4o-transcribe"}:
        return OpenAITranscribeService()
    if backend == "whisper_pyannote":
        return WhisperPyannoteTranscriptionService()
    if backend in {"whisper", "whisper_only"}:
        return WhisperOnlyTranscriptionService()
    return StubTranscriptionService()
