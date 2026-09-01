"""faster-whisper + pyannote.audio transcription backend."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List

from app.core.config import settings
from app.transcription.base import DiarizedSegment, TranscriptionService


class WhisperPyannoteTranscriptionService(TranscriptionService):
    """Production transcription using faster-whisper and pyannote diarization."""

    def __init__(self) -> None:
        from faster_whisper import WhisperModel

        self._whisper = WhisperModel(
            settings.whisper_model_size,
            device="cpu",
            compute_type="int8",
        )
        self._diarization_pipeline = None

    def _load_diarization(self):
        if self._diarization_pipeline is None:
            from pyannote.audio import Pipeline

            self._diarization_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=settings.pyannote_hf_token or True,
            )
        return self._diarization_pipeline

    def transcribe_and_diarize(self, audio_bytes: bytes, filename: str) -> List[DiarizedSegment]:
        suffix = Path(filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            audio_path = tmp.name

        try:
            whisper_segments, _ = self._whisper.transcribe(audio_path, word_timestamps=True)
            diarization = self._load_diarization()(audio_path)

            raw_segments: List[DiarizedSegment] = []
            for segment in whisper_segments:
                midpoint = (segment.start + segment.end) / 2
                speaker = self._speaker_at_time(diarization, midpoint)
                raw_segments.append(
                    DiarizedSegment(
                        speaker_label=speaker,
                        start_time=float(segment.start),
                        end_time=float(segment.end),
                        text=segment.text.strip(),
                    )
                )
            return self.merge_consecutive_segments(raw_segments)
        finally:
            Path(audio_path).unlink(missing_ok=True)

    @staticmethod
    def _speaker_at_time(diarization, timestamp: float) -> str:
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            if turn.start <= timestamp <= turn.end:
                return str(speaker)
        return "SPEAKER_UNKNOWN"
