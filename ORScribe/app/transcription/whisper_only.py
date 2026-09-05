"""faster-whisper transcription without pyannote (no Hugging Face token required)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List

from app.core.config import settings
from app.transcription.base import DiarizedSegment, TranscriptionService

_OR_INITIAL_PROMPT = (
    "Operating room anesthesia dictation. Clinical terms: dental state, mental state, "
    "weight kg, blood pressure, pulse, SpO2, temperature, ASA class, allergies, smoker, "
    "alcoholic, NPO, last meal, food date, fluid date, airway, GCS, ECG, chest X-ray. "
    "Keep dental and mental as spoken; do not swap them."
)


class WhisperOnlyTranscriptionService(TranscriptionService):
    """Transcribe real audio with faster-whisper for per-window STT."""

    def __init__(self) -> None:
        from faster_whisper import WhisperModel

        self._whisper = WhisperModel(
            settings.whisper_model_size,
            device="cpu",
            compute_type="int8",
        )

    def transcribe_and_diarize(
        self, audio_bytes: bytes, filename: str, *, time_offset: float = 0.0
    ) -> List[DiarizedSegment]:
        # Skip band-pass / noise-gate preprocessing — it strips consonants and
        # destroys short clinical dictations (verified vs raw WAV).
        suffix = Path(filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            audio_path = tmp.name

        try:
            whisper_segments, _ = self._whisper.transcribe(
                audio_path,
                language="en",
                task="transcribe",
                beam_size=5,
                best_of=5,
                vad_filter=False,
                condition_on_previous_text=False,
                word_timestamps=False,
                initial_prompt=_OR_INITIAL_PROMPT,
            )
            raw_segments: List[DiarizedSegment] = []
            for segment in whisper_segments:
                text = segment.text.strip()
                if not text:
                    continue
                raw_segments.append(
                    DiarizedSegment(
                        speaker_label="SPEAKER_00",
                        start_time=float(segment.start) + time_offset,
                        end_time=float(segment.end) + time_offset,
                        text=text,
                    )
                )
            return self.merge_consecutive_segments(raw_segments)
        finally:
            Path(audio_path).unlink(missing_ok=True)
