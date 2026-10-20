"""OpenAI cloud transcription (gpt-4o-transcribe / gpt-4o-transcribe-diarize).

Visit audio is sent to OpenAI. Use only when PHI policy allows it.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any, List

from app.core.config import settings
from app.transcription.base import DiarizedSegment, TranscriptionService

_SENTENCE_RE = re.compile(r"[^.!?؟]+[.!?؟]*")
_DIARIZE_MODELS = {"gpt-4o-transcribe-diarize"}


class GptTranscribeTranscriptionService(TranscriptionService):
    """Cloud ASR via OpenAI /v1/audio/transcriptions."""

    def __init__(self) -> None:
        from openai import OpenAI

        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for TRANSCRIPTION_BACKEND=gpt_transcribe")

        self._model = (settings.openai_transcribe_model or "gpt-4o-transcribe-diarize").strip()
        self._diarize = self._model.lower() in _DIARIZE_MODELS or self._model.lower().endswith("-diarize")
        # Long visits need more than the SDK default read timeout.
        self._client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=max(float(settings.openai_timeout), 600.0),
            max_retries=max(settings.openai_max_retries, 1),
        )

    def transcribe_and_diarize(self, audio_bytes: bytes, filename: str) -> List[DiarizedSegment]:
        suffix = Path(filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            audio_path = tmp.name

        try:
            with open(audio_path, "rb") as audio_file:
                kwargs: dict[str, Any] = {"model": self._model, "file": audio_file}
                if self._diarize:
                    kwargs["response_format"] = "diarized_json"
                    kwargs["chunking_strategy"] = "auto"
                else:
                    kwargs["response_format"] = "json"
                result = self._client.audio.transcriptions.create(**kwargs)

            if self._diarize and getattr(result, "segments", None):
                segments = self._from_diarized(result)
            else:
                text = getattr(result, "text", None) or str(result)
                segments = self._from_plain_text(text)
            return self.merge_consecutive_segments(segments)
        finally:
            Path(audio_path).unlink(missing_ok=True)

    def _from_diarized(self, result: Any) -> List[DiarizedSegment]:
        """Map API speaker labels (A/B/agent/...) onto SPEAKER_00, SPEAKER_01, ... in first-seen order."""
        speaker_ids: dict[str, str] = {}
        segments: List[DiarizedSegment] = []
        for item in result.segments or []:
            text = str(getattr(item, "text", "") or "").strip()
            if not text:
                continue
            raw_speaker = str(getattr(item, "speaker", "") or "unknown").strip() or "unknown"
            if raw_speaker not in speaker_ids:
                speaker_ids[raw_speaker] = f"SPEAKER_{len(speaker_ids):02d}"
            segments.append(
                DiarizedSegment(
                    speaker_label=speaker_ids[raw_speaker],
                    start_time=float(getattr(item, "start", 0.0) or 0.0),
                    end_time=float(getattr(item, "end", 0.0) or 0.0),
                    text=text,
                )
            )
        return segments

    def _from_plain_text(self, text: str) -> List[DiarizedSegment]:
        """No speaker turns from the API: split into sentences and alternate labels (same as whisper_only)."""
        parts = [part.strip() for part in _SENTENCE_RE.findall(text or "") if part.strip()]
        if not parts and (text or "").strip():
            parts = [text.strip()]
        segments: List[DiarizedSegment] = []
        cursor = 0.0
        for index, part in enumerate(parts):
            # Synthetic times so downstream still has an ordering; cloud text-only has no timestamps.
            duration = max(1.0, min(8.0, 0.35 * len(part.split())))
            segments.append(
                DiarizedSegment(
                    speaker_label="SPEAKER_00" if index % 2 == 0 else "SPEAKER_01",
                    start_time=cursor,
                    end_time=cursor + duration,
                    text=part,
                )
            )
            cursor += duration
        return segments
