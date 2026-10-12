"""Unit tests for role identification."""

import pytest

from app.ai.role_identification import identify_roles
from app.ai.unified_prompts import PURPOSE_FRAGMENTS, TranscriptionRequest, build_system_prompt
from tests.fixtures.sample_transcripts import (
    AMBIGUOUS_FEW_QUESTIONS,
    THREE_SPEAKER_WITH_FAMILY,
    TWO_SPEAKER_NORMAL,
)


@pytest.mark.parametrize(
    "segments,expected_doctor,expected_patient,min_confidence",
    [
        (TWO_SPEAKER_NORMAL, "SPEAKER_00", "SPEAKER_01", "high"),
        (THREE_SPEAKER_WITH_FAMILY, "SPEAKER_00", "SPEAKER_02", "high"),
    ],
)
def test_role_identification_known_cases(segments, expected_doctor, expected_patient, min_confidence):
    result = identify_roles(segments)
    assert result.role_map[expected_doctor] == "doctor"
    assert result.role_map[expected_patient] == "patient"
    assert result.confidence in {"high", "medium", "low"}
    if min_confidence == "high":
        assert result.confidence == "high"


def test_role_identification_three_speaker_family_member():
    result = identify_roles(THREE_SPEAKER_WITH_FAMILY)
    assert result.role_map["SPEAKER_01"] == "other"
    assert "SPEAKER_00" in result.role_map
    assert "SPEAKER_02" in result.role_map


def test_role_identification_ambiguous_case():
    result = identify_roles(AMBIGUOUS_FEW_QUESTIONS)
    assert result.confidence == "low"
    assert len(result.role_map) >= 2


@pytest.mark.parametrize("purpose", ["summary", "soap_note", "clinical_document", "full_transcript_review"])
def test_convoscribe_purpose_fragments_in_system_prompt(purpose):
    req = TranscriptionRequest(
        context_type="appointment",
        attendees=["doctor", "patient"],
        purpose=purpose,
        detail_level="standard",
    )
    prompt = build_system_prompt(req)
    assert PURPOSE_FRAGMENTS[purpose] in prompt
    assert "Doctor:" in prompt
    assert "Patient:" in prompt
    assert "Surgeon:" not in prompt
