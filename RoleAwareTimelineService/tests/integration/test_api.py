"""HTTP contract tests. OpenAI is mocked and is not contacted."""
import json

import pytest
from fastapi.testclient import TestClient

from app.api.routes import timeline_service
from app.core.config import settings
from main import app
from tests.fixtures.acceptance_chart import ACCEPTANCE_PATIENT, SHARED_SUMMARY
from tests.fixtures.scripted_model import ScriptedCompletions


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


def test_health_does_not_call_the_model(client, monkeypatch):
    """Health reports configuration and does not send a completion request."""

    def fail(**kwargs):
        raise AssertionError("health called OpenAI")

    monkeypatch.setattr(timeline_service.ai_client._completions, "create", fail)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "role-aware-timeline"
    assert body["provider"] == "openai"
    assert body["openai_configured"] is True
    assert body["model"] == settings.openai_model
    assert body["version"] == settings.api_version


def test_root_lists_the_configured_model(client):
    """The root payload names the configured model rather than a built-in one."""
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == settings.openai_model
    assert body["docs"] == "/docs"


def test_generate_role_timeline_for_the_acceptance_chart(client, monkeypatch):
    """POST returns the three layers for the nurse view of the acceptance chart."""
    script = ScriptedCompletions()
    monkeypatch.setattr(timeline_service.ai_client._completions, "create", script)
    payload = {
        "request_id": "api-nurse",
        "viewer_role": "nurse",
        "patient_data": {
            **ACCEPTANCE_PATIENT,
            "medications": [
                {**ACCEPTANCE_PATIENT["medications"][0], "dose": "500 mg"},
                ACCEPTANCE_PATIENT["medications"][1],
            ],
            "vitals": [{**ACCEPTANCE_PATIENT["vitals"][0], "unit": "mmHg"}],
        },
    }
    response = client.post("/api/v1/generate-role-timeline", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["clinical_summary"] == SHARED_SUMMARY
    assert body["processing_metadata"]["viewer_role"] == "nurse"
    assert body["processing_metadata"]["event_count"] == len(body["timeline"])
    assert body["processing_metadata"]["model"] == settings.openai_model
    timeline_prompt = script.calls[0]["messages"][-1]["content"]
    assert "STEP: timeline" in timeline_prompt
    assert "500 mg" not in timeline_prompt
    assert "mmHg" not in timeline_prompt
    assert "ng/mL" in timeline_prompt
    assert json.dumps(body).lower().count("mmhg") == 0


def test_missing_role_is_rejected(client):
    """viewer_role is required."""
    response = client.post(
        "/api/v1/generate-role-timeline",
        json={"patient_data": {"patient_id": "pt-1"}},
    )
    assert response.status_code == 422


def test_model_failure_is_a_client_error(client, monkeypatch):
    """A failed generation is returned as 400 and does not leak a stack trace."""

    def fail(_patient_data):
        raise ValueError("malformed model JSON")

    monkeypatch.setattr(timeline_service.ai_client, "generate_timeline", fail)
    response = client.post(
        "/api/v1/generate-role-timeline",
        json={"viewer_role": "nurse", "patient_data": {"patient_id": "pt-1"}},
    )
    assert response.status_code == 400
    assert "malformed model JSON" in response.json()["detail"]


def test_docs_are_available(client):
    """OpenAPI docs are served with the FastAPI app."""
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
