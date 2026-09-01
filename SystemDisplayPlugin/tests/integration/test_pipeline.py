"""API integration tests for reshape and stored decoders."""

from unittest.mock import patch

from tests.fixtures.sample_payloads import EHR_SOAP_CARD, SOAP_NOTE


def test_register_and_fetch_decoder(client, auth_headers):
    created = client.post("/api/v1/decoders", headers=auth_headers, json=EHR_SOAP_CARD)
    assert created.status_code == 201
    assert created.json()["view_id"] == "ehr_soap_card"

    fetched = client.get("/api/v1/decoders/ehr_soap_card", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["view_name"] == "EHR SOAP card"
    assert len(fetched.json()["fields"]) == 5


def test_reshape_with_stored_view_id(client, auth_headers):
    client.post("/api/v1/decoders", headers=auth_headers, json=EHR_SOAP_CARD)
    with patch("app.services.mapping_service.settings.use_llm_stub", False), patch(
        "app.services.mapping_service.AIClient"
    ) as mock_cls:
        mock_cls.return_value.complete_json.return_value = {
            "plan_brief": "Ibuprofen PRN; two-week follow-up.",
        }
        response = client.post(
            "/api/v1/reshape",
            headers=auth_headers,
            json={
                "stage1_output": SOAP_NOTE,
                "context": "appointment",
                "purpose": "soap_note",
                "view_id": "ehr_soap_card",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["hpi"] == SOAP_NOTE["subjective"]
    assert body["data"]["plan_brief"] == "Ibuprofen PRN; two-week follow-up."


def test_reshape_inline_decoder(client, auth_headers):
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
    response = client.post("/api/v1/reshape", headers=auth_headers, json=payload)
    assert response.status_code == 200
    assert response.json()["data"]["dx"] == "Tension-type headache."


def test_get_unknown_decoder_404(client, auth_headers):
    response = client.get("/api/v1/decoders/does-not-exist", headers=auth_headers)
    assert response.status_code == 404


def test_reshape_requires_api_key(client):
    response = client.post(
        "/api/v1/reshape",
        json={
            "stage1_output": SOAP_NOTE,
            "context": "appointment",
            "purpose": "soap_note",
            "view_decoder": EHR_SOAP_CARD,
        },
    )
    assert response.status_code == 422 or response.status_code == 401
