"""Unit tests for path resolution and mapping_service."""

from unittest.mock import MagicMock

import pytest

from app.fixtures.decoders import MEASUREMENT_DECODER, SOAP_NOTE_DECODER, VITAL_SIGNS_DECODER
from app.models.schemas import DecoderField, ViewDecoder
from app.services.mapping_service import (
    MISSING,
    AllRequiredFieldsFailed,
    resolve_path,
    reshape,
    reshape_many,
)
from tests.fixtures.sample_payloads import (
    EHR_SOAP_CARD,
    ENCOUNTER_STAGE1,
    ENCOUNTER_STAGE1_OPTIONALS_MISSING,
    SOAP_NOTE,
    TIMELINE,
)


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


def test_all_required_fields_missing_raises(client):
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
        json={
            "stage1_output": SOAP_NOTE,
            "context": "appointment",
            "purpose": "soap_note",
            "view_decoder": decoder.model_dump(),
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["results"][0]["view_id"] == "all_missing"
    assert len(detail["results"][0]["warnings"]) >= 2


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


def test_multi_view_reshape_populates_three_seed_views():
    result = reshape_many(
        ENCOUNTER_STAGE1,
        [SOAP_NOTE_DECODER, VITAL_SIGNS_DECODER, MEASUREMENT_DECODER],
        context="appointment",
        purpose="soap_note",
    )
    by_id = {item.view_id: item for item in result.results}
    assert set(by_id) == {"soap_note", "vital_signs", "measurement"}
    assert by_id["soap_note"].data["Subjective"] == SOAP_NOTE["subjective"]
    assert by_id["soap_note"].data["Plan"] == SOAP_NOTE["plan"]
    assert by_id["vital_signs"].data["Temperature"] == "36.8"
    assert by_id["vital_signs"].data["SpO2"] == "98"
    assert by_id["measurement"].data["WeightKg"] == "71.4"
    assert by_id["measurement"].data["BMI"] == "25.3"
    assert by_id["measurement"].warnings == []


def test_optional_measurement_gaps_do_not_affect_other_views():
    result = reshape_many(
        ENCOUNTER_STAGE1_OPTIONALS_MISSING,
        [SOAP_NOTE_DECODER, VITAL_SIGNS_DECODER, MEASUREMENT_DECODER],
        context="appointment",
        purpose="soap_note",
    )
    by_id = {item.view_id: item for item in result.results}
    assert by_id["soap_note"].warnings == []
    assert by_id["vital_signs"].warnings == []
    assert by_id["measurement"].data["BMI"] is None
    assert by_id["measurement"].data["HeadCircumferenceCm"] is None
    assert by_id["measurement"].data["WeightKg"] == "71.4"
    assert any("BMI" in w for w in by_id["measurement"].warnings)
    assert any("HeadCircumferenceCm" in w for w in by_id["measurement"].warnings)


def test_note_summarize_is_one_llm_call_batched_across_views():
    extra_soap = SOAP_NOTE_DECODER.model_copy(deep=True)
    extra_soap.fields.append(
        DecoderField(
            field_name="plan_brief",
            field_type="string",
            source_path="plan",
            transform="summarize",
            transform_hint="One short sentence",
            required=False,
        )
    )
    mock_client = MagicMock()
    mock_client.complete_json.return_value = {
        "soap_note::plan_brief": "Ibuprofen PRN; two-week follow-up.",
        "measurement::Note": "Weight after shoes off; reduced appetite.",
    }
    result = reshape_many(
        ENCOUNTER_STAGE1,
        [extra_soap, VITAL_SIGNS_DECODER, MEASUREMENT_DECODER],
        context="appointment",
        purpose="soap_note",
        client=mock_client,
    )
    assert mock_client.complete_json.call_count == 1
    user_prompt = mock_client.complete_json.call_args.kwargs["user_prompt"]
    assert "soap_note::plan_brief" in user_prompt
    assert "measurement::Note" in user_prompt
    by_id = {item.view_id: item for item in result.results}
    assert by_id["soap_note"].data["plan_brief"] == "Ibuprofen PRN; two-week follow-up."
    assert by_id["measurement"].data["Note"] == "Weight after shoes off; reduced appetite."


def test_one_view_required_failure_does_not_fail_batch():
    broken = ViewDecoder(
        view_id="broken_required",
        view_name="Broken",
        fields=[
            DecoderField(
                field_name="missing_a",
                field_type="string",
                source_path="nope.a",
                required=True,
            ),
            DecoderField(
                field_name="missing_b",
                field_type="string",
                source_path="nope.b",
                required=True,
            ),
        ],
    )
    result = reshape_many(
        ENCOUNTER_STAGE1,
        [SOAP_NOTE_DECODER, broken],
        context="appointment",
        purpose="soap_note",
    )
    by_id = {item.view_id: item for item in result.results}
    assert by_id["soap_note"].data["Assessment"] == SOAP_NOTE["assessment"]
    assert by_id["broken_required"].data["missing_a"] is None
    assert len(by_id["broken_required"].warnings) >= 2
