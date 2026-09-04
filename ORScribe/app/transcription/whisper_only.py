"""faster-whisper transcription without pyannote (no Hugging Face token required)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List

from app.core.config import settings
from app.transcription.audio_preprocessing import preprocess_audio
from app.transcription.base import DiarizedSegment, TranscriptionService


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
        processed = preprocess_audio(audio_bytes, filename)
        suffix = Path(filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(processed)
            audio_path = tmp.name

        try:
            whisper_segments, _ = self._whisper.transcribe(audio_path, word_timestamps=False)
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
