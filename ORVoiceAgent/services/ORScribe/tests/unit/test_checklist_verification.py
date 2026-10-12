"""Unit tests for WHO checklist verification."""

from app.ai.checklist_verification import verify_checklist
from app.ai.unified_prompts import PURPOSE_FRAGMENTS, TranscriptionRequest, build_system_prompt
from tests.fixtures.sample_transcripts import CHECKLIST_INCOMPLETE, THREE_ROLE_STANDARD


def test_checklist_complete_case():
    role_map = {
        "SPEAKER_00": {"role": "surgeon"},
        "SPEAKER_01": {"role": "anesthetist"},
        "SPEAKER_02": {"role": "nurse"},
    }
    result = verify_checklist(THREE_ROLE_STANDARD, role_map)
    assert result.sign_in.completed is True
    assert result.time_out.completed is True
    assert result.sign_out.completed is True


def test_checklist_reports_missing_items():
    role_map = {
        "SPEAKER_00": {"role": "surgeon"},
        "SPEAKER_02": {"role": "nurse"},
    }
    result = verify_checklist(CHECKLIST_INCOMPLETE, role_map)
    assert result.time_out.completed is False
    assert len(result.time_out.items_missing) > 0
    assert result.sign_out.completed is False
    assert len(result.sign_out.items_missing) > 0


def test_checklist_verification_purpose_fragment_in_system_prompt():
    req = TranscriptionRequest(
        context_type="operating_room",
        attendees=["surgeon", "nurse"],
        purpose="checklist_verification",
        detail_level="standard",
    )
    prompt = build_system_prompt(req)
    assert PURPOSE_FRAGMENTS["checklist_verification"] in prompt
    assert '"sign_in"' in prompt or '"sign_in":' in prompt
    assert "time_out" in prompt
