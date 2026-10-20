"""GPT cloud transcription backend (mocked; no network)."""

from types import SimpleNamespace

import pytest

from app.transcription.gpt_transcribe import GptTranscribeTranscriptionService


@pytest.fixture
def gpt_service():
    # Build without touching global settings (avoids leaking gpt_transcribe into other tests).
    service = GptTranscribeTranscriptionService.__new__(GptTranscribeTranscriptionService)
    service._model = "gpt-4o-transcribe-diarize"
    service._diarize = True
    service._client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace()))
    return service


def test_diarized_segments_map_to_speaker_labels(gpt_service):
    result = SimpleNamespace(
        segments=[
            SimpleNamespace(speaker="A", text="What brings you in?", start=0.0, end=2.0),
            SimpleNamespace(speaker="B", text="I have a headache.", start=2.1, end=4.0),
            SimpleNamespace(speaker="A", text="Any fever?", start=4.1, end=5.0),
        ]
    )
    segments = gpt_service._from_diarized(result)
    merged = gpt_service.merge_consecutive_segments(segments)
    assert [(s.speaker_label, s.text) for s in merged] == [
        ("SPEAKER_00", "What brings you in?"),
        ("SPEAKER_01", "I have a headache."),
        ("SPEAKER_00", "Any fever?"),
    ]


def test_plain_text_alternates_speakers(gpt_service):
    gpt_service._diarize = False
    segments = gpt_service._from_plain_text("Hello doctor. I feel sick.")
    assert len(segments) == 2
    assert segments[0].speaker_label == "SPEAKER_00"
    assert segments[1].speaker_label == "SPEAKER_01"
