"""Single-speaker per-window transcription (stateless STT)."""

from app.core.config import settings
from app.fixtures.window_transcripts import WINDOW_STUB_TRANSCRIPTS
from app.transcription import get_transcription_service


# TODO: add STT-only fast path (skip pyannote diarization for single-speaker window clips)


def transcribe_window_audio(audio_bytes: bytes, filename: str, *, window_id: str) -> str:
    """Transcribe a short single-speaker clip and return one concatenated text block.

    Reuses the existing transcription backend (stub or whisper_pyannote). Speaker
    labels from diarization are ignored; segment texts are joined in order.

    When TRANSCRIPTION_BACKEND=stub, returns a window-specific sample dictation so
    downstream field extraction matches the active EMR sub-tab.
    """
    if settings.transcription_backend.lower() == "stub":
        stub_text = WINDOW_STUB_TRANSCRIPTS.get(window_id)
        if stub_text:
            return stub_text

    service = get_transcription_service()
    segments = service.transcribe_and_diarize(audio_bytes, filename)
    parts = [seg.text.strip() for seg in segments if seg.text and seg.text.strip()]
    return " ".join(parts)
