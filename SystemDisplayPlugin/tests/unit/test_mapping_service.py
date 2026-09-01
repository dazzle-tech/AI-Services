"""Unit tests for path resolution and mapping_service."""

from unittest.mock import MagicMock

import pytest

from app.models.schemas import DecoderField, ViewDecoder
from app.services.mapping_service import (
    MISSING,
    AllRequiredFieldsFailed,
    resolve_path,
    reshape,
)
from tests.fixtures.sample_payloads import EHR_SOAP_CARD, SOAP_NOTE, TIMELINE


def test_resolve_path_dot_notation():
    assert resolve_path(SOAP_NOTE, "assessment") == "Tension-type headache."
    assert resolve_path(SOAP_NOTE, "medications_mentioned") == ["ibuprofen"]


def test_resolve_path_list_flattening():
    assert resolve_path(TIMELINE, "events[*].timestamp") == ["00:00:22", "00:01:10"]
    assert resolve_path(TIMELINE, "medications_administered[*].drug") == ["propofol"]


def test_resolve_path_missing_returns_sentinel():
    assert resolve_path(SOAP_NOTE, "does.not.exist") is MISSING
    assert resolve_path(SOAP_NOTE, "") is MISSING


def test_missing_optional_field_is_warning_not_failure():
    decoder = ViewDecoder(
        view_id="optional_missing",
        view_name="Optional missing",
        fields=[
            DecoderField(
                field_name="dx",
                field_type="string",
                source_path="assessment",
                required=True,
            ),
            DecoderField(
                field_name="allergy",
                field_type="string",
                source_path="allergies",
                required=False,
            ),
        ],
    )
    result = reshape(SOAP_NOTE, decoder, context="appointment", purpose="soap_note")
    assert result.data["dx"] == "Tension-type headache."
    assert result.data["allergy"] is None
    assert any("Optional field 'allergy'" in w for w in result.warnings)


def test_missing_required_field_with_others_present_is_warning():
    decoder = ViewDecoder(
        view_id="one_required_missing",
        view_name="One required missing",
        fields=[
            DecoderField(
                field_name="dx",
                field_type="string",
                source_path="assessment",
                required=True,
            ),
            DecoderField(
                field_name="vitals",
                field_type="string",
                source_path="objective.vitals",
                required=True,
            ),
        ],
    )
    result = reshape(SOAP_NOTE, decoder, context="appointment", purpose="soap_note")
    assert result.data["dx"] == "Tension-type headache."
    assert result.data["vitals"] is None
    assert any("Required field 'vitals'" in w for w in result.warnings)


def test_all_required_fields_missing_raises(client, auth_headers):
    decoder = ViewDecoder(
        view_id="all_missing",
        view_name="All missing",
        fields=[
            DecoderField(
                field_name="a",
                field_type="string",
                source_path="missing_a",
                required=True,
            ),
            DecoderField(
                field_name="b",
                field_type="string",
                source_path="missing_b",
                required=True,
            ),
        ],
    )
    with pytest.raises(AllRequiredFieldsFailed):
        reshape(SOAP_NOTE, decoder, context="appointment", purpose="soap_note")

    response = client.post(
        "/api/v1/reshape",
        headers=auth_headers,
        json={
            "stage1_output": SOAP_NOTE,
            "context": "appointment",
            "purpose": "soap_note",
            "view_decoder": decoder.model_dump(),
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["view_id"] == "all_missing"
    assert len(detail["warnings"]) >= 2


def test_summarize_transform_triggers_exactly_one_batched_llm_call():
    decoder = ViewDecoder(
        view_id="batched",
        view_name="Batched LLM",
        fields=[
            DecoderField(
                field_name="dx",
                field_type="string",
                source_path="assessment",
                required=True,
            ),
            DecoderField(
                field_name="plan_brief",
                field_type="string",
                source_path="plan",
                transform="summarize",
                transform_hint="One short sentence",
                required=True,
            ),
            DecoderField(
                field_name="hpi_brief",
                field_type="string",
                source_path="subjective",
                transform="summarize",
                transform_hint="Condense to one clause",
                required=True,
            ),
        ],
    )
    mock_client = MagicMock()
    mock_client.complete_json.return_value = {
        "plan_brief": "Ibuprofen PRN; review in two weeks.",
        "hpi_brief": "3-day frontal headache, no fever.",
    }
    result = reshape(
        SOAP_NOTE,
        decoder,
        context="appointment",
        purpose="soap_note",
        client=mock_client,
    )
    assert mock_client.complete_json.call_count == 1
    assert result.data["dx"] == "Tension-type headache."
    assert result.data["plan_brief"] == "Ibuprofen PRN; review in two weeks."
    assert result.data["hpi_brief"] == "3-day frontal headache, no fever."


def test_end_to_end_soap_note_reshape_field_by_field():
    decoder = ViewDecoder.model_validate(EHR_SOAP_CARD)
    mock_client = MagicMock()
    mock_client.complete_json.return_value = {
        "plan_brief": "Ibuprofen as needed; follow up in two weeks.",
    }
    result = reshape(
        SOAP_NOTE,
        decoder,
        context="appointment",
        purpose="soap_note",
        client=mock_client,
    )
    assert result.view_id == "ehr_soap_card"
    assert list(result.data.keys()) == ["hpi", "exam", "dx", "meds", "plan_brief"]
    assert result.data["hpi"] == SOAP_NOTE["subjective"]
    assert result.data["exam"] == SOAP_NOTE["objective"]
    assert result.data["dx"] == SOAP_NOTE["assessment"]
    assert result.data["meds"] == ["ibuprofen"]
    assert result.data["plan_brief"] == "Ibuprofen as needed; follow up in two weeks."
    assert result.warnings == []
    assert mock_client.complete_json.call_count == 1
