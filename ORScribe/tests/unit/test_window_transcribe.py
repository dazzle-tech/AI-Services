"""Unit tests for per-window transcription."""

from unittest.mock import patch

from app.transcription.base import DiarizedSegment
from app.services.window_transcribe_service import transcribe_window_audio


def test_concatenates_segment_text_in_order_ignoring_speakers():
    segments = [
        DiarizedSegment("SPEAKER_00", 0.0, 2.0, "Patient identity confirmed."),
        DiarizedSegment("SPEAKER_01", 2.0, 4.0, "Site marked left knee."),
        DiarizedSegment("SPEAKER_00", 4.0, 6.0, "Consent verified."),
    ]

    class FakeService:
        def transcribe_and_diarize(self, audio_bytes, filename, *, time_offset=0.0):
            del audio_bytes, filename, time_offset
            return segments

    with patch(
        "app.services.window_transcribe_service.get_transcription_service",
        return_value=FakeService(),
    ), patch(
        "app.services.window_transcribe_service.settings.transcription_backend",
        "whisper_pyannote",
    ):
        text = transcribe_window_audio(b"fake", "clip.wav", window_id="nursing_time_out")

    assert text == "Patient identity confirmed. Site marked left knee. Consent verified."


def test_skips_empty_segments():
    segments = [
        DiarizedSegment("SPEAKER_00", 0.0, 1.0, "  "),
        DiarizedSegment("SPEAKER_00", 1.0, 2.0, "Time out complete."),
        DiarizedSegment("SPEAKER_00", 2.0, 3.0, ""),
    ]

    class FakeService:
        def transcribe_and_diarize(self, audio_bytes, filename, *, time_offset=0.0):
            del audio_bytes, filename, time_offset
            return segments

    with patch(
        "app.services.window_transcribe_service.get_transcription_service",
        return_value=FakeService(),
    ), patch(
        "app.services.window_transcribe_service.settings.transcription_backend",
        "whisper_pyannote",
    ):
        text = transcribe_window_audio(b"fake", "clip.wav", window_id="nursing_time_out")

    assert text == "Time out complete."


def test_stub_backend_returns_window_specific_text():
    with patch(
        "app.services.window_transcribe_service.settings.transcription_backend",
        "stub",
    ):
        text = transcribe_window_audio(b"fake", "clip.wav", window_id="nursing_intraoperative")
    assert "Operation date 2026-09-03" in text
