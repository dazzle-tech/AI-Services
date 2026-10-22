"""Transcription backend factory."""

from app.core.config import settings
from app.transcription.base import TranscriptionService
from app.transcription.gpt_transcribe import GptTranscribeTranscriptionService
from app.transcription.stub import StubTranscriptionService
from app.transcription.whisper_only import WhisperOnlyTranscriptionService
from app.transcription.whisper_pyannote import WhisperPyannoteTranscriptionService


def get_transcription_service() -> TranscriptionService:
    backend = (settings.transcription_backend or "gpt_transcribe").strip().lower()
    if backend in {"gpt_transcribe", "openai", "gpt-4o-transcribe"}:
        return GptTranscribeTranscriptionService()
    if backend == "whisper_pyannote":
        return WhisperPyannoteTranscriptionService()
    if backend in {"whisper", "whisper_only"}:
        return WhisperOnlyTranscriptionService()
    if backend == "stub":
        return StubTranscriptionService()
    raise RuntimeError(
        f"Unknown TRANSCRIPTION_BACKEND={settings.transcription_backend!r}. "
        "Use gpt_transcribe, whisper, whisper_pyannote, or stub."
    )
