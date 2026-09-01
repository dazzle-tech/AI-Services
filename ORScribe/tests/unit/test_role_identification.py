"""Unit tests for OR role identification."""

import pytest

from app.ai.role_identification import identify_roles
from app.ai.unified_prompts import PURPOSE_FRAGMENTS, TranscriptionRequest, build_system_prompt
from tests.fixtures.sample_transcripts import (
    AMBIGUOUS_LOW_CONFIDENCE,
    FOUR_SPEAKER_WITH_RESIDENT,
    THREE_ROLE_STANDARD,
)


def test_role_identification_three_role_case():
    result = identify_roles(THREE_ROLE_STANDARD)
    assert result.role_map["SPEAKER_00"].role == "surgeon"
    assert result.role_map["SPEAKER_01"].role == "anesthetist"
    assert result.role_map["SPEAKER_02"].role == "nurse"
    assert result.role_map["SPEAKER_00"].confidence == "high"
    assert not result.role_map["SPEAKER_00"].needs_review


def test_role_identification_fourth_person():
    result = identify_roles(FOUR_SPEAKER_WITH_RESIDENT)
    assert result.role_map["SPEAKER_03"].role == "unidentified"
    assert result.role_map["SPEAKER_03"].confidence == "low"
    assert result.role_map["SPEAKER_03"].needs_review is True
    assert result.role_map["SPEAKER_00"].role == "surgeon"


def test_role_identification_ambiguous_case():
    result = identify_roles(AMBIGUOUS_LOW_CONFIDENCE)
    assert all(a.confidence == "low" for a in result.role_map.values())
    assert all(a.needs_review for a in result.role_map.values())


@pytest.mark.parametrize(
    "purpose",
    ["timeline", "checklist_verification", "full_transcript_review"],
)
def test_orscribe_purpose_fragments_in_system_prompt(purpose):
    req = TranscriptionRequest(
        context_type="operating_room",
        attendees=["surgeon", "anesthetist", "nurse"],
        purpose=purpose,
        detail_level="standard",
    )
    prompt = build_system_prompt(req)
    assert PURPOSE_FRAGMENTS[purpose] in prompt
    assert "operating room" in prompt.lower() or "Surgeon:" in prompt
    assert "Surgeon:" in prompt
    assert "Anesthetist" in prompt
    assert "Patient:" not in prompt
