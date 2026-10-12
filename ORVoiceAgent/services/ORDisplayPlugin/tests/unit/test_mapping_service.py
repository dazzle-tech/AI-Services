"""Unit tests for ORScribe path mapping."""

import pytest

from app.fixtures.decoders import (
    OR_CHECKLIST_DECODER,
    OR_COUNTS_DECODER,
    OR_MEDICATIONS_DECODER,
    OR_ROLES_DECODER,
    OR_TIMELINE_DECODER,
)
from app.models.schemas import DecoderField, ViewDecoder
from app.services.mapping_service import MISSING, AllRequiredFieldsFailed, resolve_path, reshape, reshape_many
from app.services.orscribe_adapter import normalize_orscribe_output
from tests.fixtures.sample_payloads import ANALYZE_AUDIO, CASE_RECORD


def test_normalize_analyze_flattens_timeline_and_checklist():
    flat = normalize_orscribe_output(ANALYZE_AUDIO)
    assert flat["events"][0]["type"] == "incision"
    assert flat["medications_administered"][0]["drug"] == "propofol"
    assert flat["sign_in"]["completed"] is True
    assert flat["time_out"]["completed"] is True
    assert flat["sign_out"]["completed"] is True


def test_normalize_case_record_uses_medications_and_checklist_result():
    flat = normalize_orscribe_output(CASE_RECORD)
    assert flat["procedure_type"] == "laparoscopic cholecystectomy"
    assert flat["medications_administered"][0]["dose"] == "100 mg"
    assert flat["instrument_counts"][0]["result"] == "correct"
    assert flat["sign_out"]["items_confirmed"] == ["procedure recorded", "specimen labeled"]


def test_resolve_path_orscribe_lists():
    flat = normalize_orscribe_output(ANALYZE_AUDIO)
    assert resolve_path(flat, "events[*].timestamp") == ["00:00:22", "00:01:10"]
    assert resolve_path(flat, "medications_administered[*].drug") == ["propofol"]
    assert resolve_path(flat, "does.not.exist") is MISSING


def test_reshape_seeded_views_from_analyze():
    flat = normalize_orscribe_output(ANALYZE_AUDIO)
    result = reshape_many(
        flat,
        [
            OR_TIMELINE_DECODER,
            OR_MEDICATIONS_DECODER,
            OR_COUNTS_DECODER,
            OR_CHECKLIST_DECODER,
            OR_ROLES_DECODER,
        ],
        context="operating_room",
        purpose="timeline",
    )
    by_id = {item.view_id: item for item in result.results}
    assert by_id["or_timeline"].data["Events"][0]["description"] == "Incision made"
    assert by_id["or_medications"].data["Drugs"] == ["propofol"]
    assert by_id["or_counts"].data["CountResults"] == ["correct"]
    assert by_id["or_checklist"].data["SignInCompleted"] is True
    assert by_id["or_checklist"].data["SignOutCompleted"] is True
    assert by_id["or_roles"].data["NeedsReview"] is False
    assert by_id["or_roles"].data["RoleMap"]["SPEAKER_00"]["role"] == "surgeon"


def test_all_required_fields_missing_raises():
    decoder = ViewDecoder(
        view_id="all_missing",
        view_name="All missing",
        fields=[
            DecoderField(field_name="a", field_type="string", source_path="missing_a", required=True),
            DecoderField(field_name="b", field_type="string", source_path="missing_b", required=True),
        ],
    )
    with pytest.raises(AllRequiredFieldsFailed):
        reshape(ANALYZE_AUDIO, decoder, context="operating_room", purpose="timeline")
