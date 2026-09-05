"""OpenAI cloud STT via gpt-4o-transcribe (Audio Transcriptions API)."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import List

from openai import OpenAI

from app.core.config import settings
from app.transcription.base import DiarizedSegment, TranscriptionService

logger = logging.getLogger(__name__)

_OR_PROMPT = (
    "Operating room anesthesia / nursing dictation. Transcribe exactly what was spoken. "
    "If the speaker says 'dental state', write 'dental state' — never substitute 'mental state'. "
    "Clinical wording examples: dental state, mallampati, open mouth, thyromental distance, "
    "neck mobility, mental state, allergies, smoker, alcoholic, weight kg, blood pressure, "
    "pulse, SpO2, temperature, ASA class, NPO, last meal, food date, fluid date."
)


class OpenAITranscribeService(TranscriptionService):
    """Transcribe real audio with OpenAI gpt-4o-transcribe (or configured model)."""

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required when TRANSCRIPTION_BACKEND=openai"
            )
        self._client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=settings.openai_timeout,
            max_retries=settings.openai_max_retries,
        )
        self._model = settings.openai_transcribe_model

    def transcribe_and_diarize(
        self, audio_bytes: bytes, filename: str, *, time_offset: float = 0.0
    ) -> List[DiarizedSegment]:
        if not audio_bytes:
            return []

        suffix = Path(filename).suffix.lower() or ".wav"
        safe_name = Path(filename).name or f"audio{suffix}"
        buffer = io.BytesIO(audio_bytes)
        buffer.name = safe_name

        try:
            result = self._client.audio.transcriptions.create(
                model=self._model,
                file=buffer,
                language="en",
                prompt=_OR_PROMPT,
                response_format="json",
            )
        except Exception:
            logger.exception("OpenAI transcription failed model=%s", self._model)
            raise

        text = (getattr(result, "text", None) or "").strip()
        if not text:
            return []

        if settings.enable_usage_tracking:
            usage = getattr(result, "usage", None)
            if usage is not None:
                logger.info(
                    "OpenAI transcription usage model=%s usage=%s",
                    self._model,
                    usage,
                )

        return [
            DiarizedSegment(
                speaker_label="SPEAKER_00",
                start_time=float(time_offset),
                end_time=float(time_offset),
                text=text,
            )
        ]
