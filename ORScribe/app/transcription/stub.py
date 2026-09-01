"""Deterministic stub transcription for local dev and tests."""

from typing import List

from app.transcription.base import DiarizedSegment, TranscriptionService


class StubTranscriptionService(TranscriptionService):
    """Returns OR-specific canned diarized transcript without running ML models."""

    DEFAULT_TRANSCRIPT: List[DiarizedSegment] = [
        DiarizedSegment("SPEAKER_00", 0.0, 8.0, "Sign in complete. Patient identity confirmed, site marked."),
        DiarizedSegment(
            "SPEAKER_01",
            8.5,
            15.0,
            "Anesthesia plan reviewed. Allergies noted. Consent verified.",
        ),
        DiarizedSegment(
            "SPEAKER_02",
            15.5,
            22.0,
            "Time out. Team introductions. Anticipated critical events reviewed.",
        ),
        DiarizedSegment("SPEAKER_00", 22.5, 28.0, "Making incision now. Scalpel."),
        DiarizedSegment(
            "SPEAKER_01",
            28.5,
            35.0,
            "Blood pressure 120 over 80. Heart rate 72. Giving propofol 100 milligrams.",
        ),
        DiarizedSegment(
            "SPEAKER_02",
            35.5,
            42.0,
            "Sponge count correct. Instrument count correct.",
        ),
        DiarizedSegment(
            "SPEAKER_00",
            48.5,
            55.0,
            "Sign out. Procedure recorded as laparoscopic cholecystectomy. Specimen labeled.",
        ),
    ]

    CHUNK_TWO_TRANSCRIPT: List[DiarizedSegment] = [
        DiarizedSegment("SPEAKER_00", 0.0, 6.0, "Closing fascia. Suture please."),
        DiarizedSegment("SPEAKER_01", 6.5, 12.0, "Vitals stable. Blood pressure 118 over 76."),
        DiarizedSegment("SPEAKER_02", 12.5, 18.0, "Final instrument count correct. Sponge count correct."),
    ]

    def transcribe_and_diarize(
        self, audio_bytes: bytes, filename: str, *, time_offset: float = 0.0
    ) -> List[DiarizedSegment]:
        del audio_bytes, filename
        source = self.CHUNK_TWO_TRANSCRIPT if time_offset > 0 else self.DEFAULT_TRANSCRIPT
        segments = [
            DiarizedSegment(
                speaker_label=s.speaker_label,
                start_time=s.start_time + time_offset,
                end_time=s.end_time + time_offset,
                text=s.text,
            )
            for s in source
        ]
        return self.merge_consecutive_segments(segments)
