"""API integration tests for reshape and stored decoders."""

from unittest.mock import patch

from tests.fixtures.sample_payloads import (
    EHR_SOAP_CARD,
    ENCOUNTER_STAGE1,
    ENCOUNTER_STAGE1_OPTIONALS_MISSING,
    SOAP_NOTE,
    full_chart_reshape_request,
)


def test_register_and_fetch_decoder(client):
    created = client.post("/api/v1/decoders", json=EHR_SOAP_CARD)
    assert created.status_code == 201
    assert created.json()["view_id"] == "ehr_soap_card"

    fetched = client.get("/api/v1/decoders/ehr_soap_card")
    assert fetched.status_code == 200
    assert fetched.json()["view_name"] == "EHR SOAP card"
    assert len(fetched.json()["fields"]) == 5


def test_reshape_with_stored_view_id(client):
    client.post("/api/v1/decoders", json=EHR_SOAP_CARD)
    with patch("app.services.mapping_service.settings.use_llm_stub", False), patch(
        "app.services.mapping_service.AIClient"
    ) as mock_cls:
        mock_cls.return_value.complete_json.return_value = {
            "plan_brief": "Ibuprofen PRN; two-week follow-up.",
        }
        response = client.post(
            "/api/v1/reshape",
            json={
                "stage1_output": SOAP_NOTE,
                "context": "appointment",
                "purpose": "soap_note",
                "view_id": "ehr_soap_card",
            },
        )
    assert response.status_code == 200
    body = response.json()
    card = next(item for item in body["results"] if item["view_id"] == "ehr_soap_card")
    assert card["data"]["hpi"] == SOAP_NOTE["subjective"]
    assert card["data"]["plan_brief"] == "Ibuprofen PRN; two-week follow-up."


def test_reshape_inline_decoder(client):
    payload = {
        "stage1_output": SOAP_NOTE,
        "context": "appointment",
        "purpose": "soap_note",
        "view_decoder": {
            "view_id": "inline_card",
            "view_name": "Inline",
            "fields": [
                {
                    "field_name": "dx",
                    "field_type": "string",
                    "source_path": "assessment",
                    "transform": "direct",
                    "required": True,
                }
            ],
        },
    }
    response = client.post("/api/v1/reshape", json=payload)
    assert response.status_code == 200
    assert response.json()["results"][0]["data"]["dx"] == "Tension-type headache."


def test_get_unknown_decoder_404(client):
    response = client.get("/api/v1/decoders/does-not-exist")
    assert response.status_code == 404


def test_reshape_full_inline_chart_views(client):
    response = client.post("/api/v1/reshape", json=full_chart_reshape_request())
    assert response.status_code == 200
    by_id = {item["view_id"]: item for item in response.json()["results"]}
    assert set(by_id) == {"soap_note", "vital_signs", "measurement"}
    soap = by_id["soap_note"]["data"]
    assert soap["Assessments"] == SOAP_NOTE["assessment"]
    assert "ChiefComplaint" in soap
    assert "HPI" in soap
    assert "TreatmentPlans" in soap
    assert by_id["vital_signs"]["data"]["Temperature"] == "36.8"
    assert by_id["measurement"]["data"]["WeightKg"] == "71.4"


def test_reshape_does_not_require_headers(client):
    response = client.post(
        "/api/v1/reshape",
        json={
            "stage1_output": SOAP_NOTE,
            "context": "appointment",
            "purpose": "soap_note",
            "view_decoder": EHR_SOAP_CARD,
        },
    )
    assert response.status_code == 200
    assert response.json()["results"]


def test_reshape_three_seeded_views_in_one_call(client):
    with patch("app.services.mapping_service.settings.use_llm_stub", False), patch(
        "app.services.mapping_service.AIClient"
    ) as mock_cls:
        mock_cls.return_value.complete_json.return_value = {
            "soap_note::HPI": SOAP_NOTE["subjective"],
            "measurement::Note": "Weight after shoes off; reduced appetite.",
            "Note": "Weight after shoes off; reduced appetite.",
        }
        response = client.post(
            "/api/v1/reshape",
            json={
                "stage1_output": ENCOUNTER_STAGE1,
                "context": "appointment",
                "purpose": "soap_note",
                "view_ids": ["soap_note", "vital_signs", "measurement"],
            },
        )
    assert response.status_code == 200
    by_id = {item["view_id"]: item for item in response.json()["results"]}
    assert set(by_id) == {"soap_note", "vital_signs", "measurement"}
    assert by_id["soap_note"]["data"]["Assessments"] == SOAP_NOTE["assessment"]
    assert by_id["soap_note"]["data"]["HPI"] == SOAP_NOTE["subjective"]
    assert by_id["vital_signs"]["data"]["PulseRate"] == "72"
    assert by_id["measurement"]["data"]["HeightLengthCm"] == "168"
    assert mock_cls.return_value.complete_json.call_count == 1


def test_reshape_optional_gaps_isolated_to_measurement_view(client):
    response = client.post(
        "/api/v1/reshape",
        json={
            "stage1_output": ENCOUNTER_STAGE1_OPTIONALS_MISSING,
            "context": "appointment",
            "purpose": "soap_note",
            "view_ids": ["soap_note", "vital_signs", "measurement"],
        },
    )
    assert response.status_code == 200
    by_id = {item["view_id"]: item for item in response.json()["results"]}
    assert by_id["soap_note"]["warnings"] == []
    assert by_id["vital_signs"]["warnings"] == []
    assert by_id["measurement"]["data"]["BMI"] is None
    assert by_id["measurement"]["data"]["HeadCircumferenceCm"] is None
    assert any("BMI" in w for w in by_id["measurement"]["warnings"])


def test_reshape_one_failed_view_does_not_422_when_others_succeed(client):
    response = client.post(
        "/api/v1/reshape",
        json={
            "stage1_output": SOAP_NOTE,
            "context": "appointment",
            "purpose": "soap_note",
            "view_ids": ["soap_note", "vital_signs"],
        },
    )
    assert response.status_code == 200
    by_id = {item["view_id"]: item for item in response.json()["results"]}
    assert by_id["soap_note"]["data"]["Assessments"] == SOAP_NOTE["assessment"]
    assert by_id["vital_signs"]["data"]["Temperature"] is None
    assert len(by_id["vital_signs"]["warnings"]) >= 1
