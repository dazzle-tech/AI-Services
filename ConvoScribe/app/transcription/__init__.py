"""Transcription backend factory."""

from app.core.config import settings
from app.transcription.base import TranscriptionService
from app.transcription.stub import StubTranscriptionService
from app.transcription.whisper_pyannote import WhisperPyannoteTranscriptionService


def get_transcription_service() -> TranscriptionService:
    backend = settings.transcription_backend.lower()
    if backend == "whisper_pyannote":
        return WhisperPyannoteTranscriptionService()
    return StubTranscriptionService()
