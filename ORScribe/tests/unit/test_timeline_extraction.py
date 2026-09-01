"""Unit tests for timeline/medication/count extraction."""

from app.ai.timeline_extraction import extract_timeline
from app.ai.unified_prompts import PURPOSE_FRAGMENTS, TranscriptionRequest, build_system_prompt
from tests.fixtures.sample_transcripts import (
    COUNT_AMBIGUOUS,
    MEDICATION_NO_DOSE,
    MEDICATION_WITH_DOSE,
    THREE_ROLE_STANDARD,
)


def test_medication_extracted_when_dose_stated():
    role_map = {"SPEAKER_01": {"role": "anesthetist"}}
    result = extract_timeline(MEDICATION_WITH_DOSE, role_map)
    assert len(result.medications_administered) == 1
    assert result.medications_administered[0].drug == "propofol"
    assert "100" in result.medications_administered[0].dose


def test_medication_not_hallucinated_without_dose():
    role_map = {"SPEAKER_01": {"role": "anesthetist"}}
    result = extract_timeline(MEDICATION_NO_DOSE, role_map)
    assert len(result.medications_administered) == 0


def test_count_not_hallucinated_when_ambiguous():
    role_map = {"SPEAKER_02": {"role": "nurse"}}
    result = extract_timeline(COUNT_AMBIGUOUS, role_map)
    assert len(result.instrument_counts) == 0


def test_timeline_preserves_timestamps():
    role_map = {
        "SPEAKER_00": {"role": "surgeon"},
        "SPEAKER_01": {"role": "anesthetist"},
        "SPEAKER_02": {"role": "nurse"},
    }
    result = extract_timeline(THREE_ROLE_STANDARD, role_map)
    incision_events = [e for e in result.events if e.type == "incision"]
    assert len(incision_events) >= 1
    assert incision_events[0].timestamp == "00:00:22"


def test_timeline_purpose_fragment_in_system_prompt():
    req = TranscriptionRequest(
        context_type="operating_room",
        attendees=["surgeon", "anesthetist"],
        purpose="timeline",
        detail_level="verbatim",
    )
    prompt = build_system_prompt(req)
    assert PURPOSE_FRAGMENTS["timeline"] in prompt
    assert "medications_administered" in prompt
