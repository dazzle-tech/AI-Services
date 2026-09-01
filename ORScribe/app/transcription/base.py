"""Transcription service abstractions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class DiarizedSegment:
    speaker_label: str
    start_time: float
    end_time: float
    text: str


class TranscriptionService(ABC):
    """Interface for speech-to-text + speaker diarization backends."""

    @abstractmethod
    def transcribe_and_diarize(
        self, audio_bytes: bytes, filename: str, *, time_offset: float = 0.0
    ) -> List[DiarizedSegment]:
        """Return merged diarized transcript segments with optional time offset."""

    @staticmethod
    def merge_consecutive_segments(segments: List[DiarizedSegment]) -> List[DiarizedSegment]:
        if not segments:
            return []

        merged: List[DiarizedSegment] = [segments[0]]
        for segment in segments[1:]:
            last = merged[-1]
            if segment.speaker_label == last.speaker_label:
                merged[-1] = DiarizedSegment(
                    speaker_label=last.speaker_label,
                    start_time=last.start_time,
                    end_time=segment.end_time,
                    text=f"{last.text} {segment.text}".strip(),
                )
            else:
                merged.append(segment)
        return merged
