"""Deterministic stub transcription for local dev and tests."""

from typing import List

from app.transcription.base import DiarizedSegment, TranscriptionService


class StubTranscriptionService(TranscriptionService):
    """Returns a canned diarized transcript without running ML models."""

    DEFAULT_TRANSCRIPT: List[DiarizedSegment] = [
        DiarizedSegment("SPEAKER_00", 0.0, 4.2, "Good morning. What brings you in today?"),
        DiarizedSegment("SPEAKER_01", 4.5, 9.8, "I've had a sore throat and fever for three days."),
        DiarizedSegment(
            "SPEAKER_00",
            10.0,
            15.5,
            "Any difficulty swallowing? I'll examine your throat and check your temperature.",
        ),
        DiarizedSegment("SPEAKER_01", 16.0, 20.0, "Swallowing hurts a little. No other symptoms."),
        DiarizedSegment(
            "SPEAKER_00",
            20.5,
            28.0,
            "Likely viral pharyngitis. Rest, fluids, acetaminophen as needed. Follow up if worsening.",
        ),
    ]

    def transcribe_and_diarize(self, audio_bytes: bytes, filename: str) -> List[DiarizedSegment]:
        del audio_bytes, filename
        return self.merge_consecutive_segments(list(self.DEFAULT_TRANSCRIPT))
