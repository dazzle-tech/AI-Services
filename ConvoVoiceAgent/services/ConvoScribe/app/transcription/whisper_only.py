"""faster-whisper transcription without pyannote (no Hugging Face token required)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List

from app.core.config import settings
from app.transcription.base import DiarizedSegment, TranscriptionService


def _whisper_runtime() -> tuple[str, str]:
    """Use the GPU when this machine has one. CPU stays on int8."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


class WhisperOnlyTranscriptionService(TranscriptionService):
    """Transcribe real audio with faster-whisper; alternate speakers per segment."""

    def __init__(self) -> None:
        from faster_whisper import WhisperModel

        device, compute_type = _whisper_runtime()
        self._whisper = WhisperModel(
            settings.whisper_model_size,
            device=device,
            compute_type=compute_type,
        )

    def transcribe_and_diarize(self, audio_bytes: bytes, filename: str) -> List[DiarizedSegment]:
        suffix = Path(filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            audio_path = tmp.name

        try:
            whisper_segments, _ = self._whisper.transcribe(
                audio_path,
                word_timestamps=False,
                vad_filter=True,
                beam_size=5,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            raw_segments: List[DiarizedSegment] = []
            for index, segment in enumerate(whisper_segments):
                text = segment.text.strip()
                if not text:
                    continue
                raw_segments.append(
                    DiarizedSegment(
                        speaker_label="SPEAKER_00" if index % 2 == 0 else "SPEAKER_01",
                        start_time=float(segment.start),
                        end_time=float(segment.end),
                        text=text,
                    )
                )
            return self.merge_consecutive_segments(raw_segments)
        finally:
            Path(audio_path).unlink(missing_ok=True)
