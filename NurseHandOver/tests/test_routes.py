"""API tests — generate must succeed with no request headers."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.schemas import GenerateSummaryResponse, PatientSummaryResult
from main import app

MINIMAL_BODY = {
    "shift_id": "shift-minimal",
    "nurse_id": "nurse_001",
    "patients": [{"patient_id": "pt_min", "name": "Alex Rivera"}],
}


@pytest.fixture
def client():
    return TestClient(app)


def _fake_response():
    stamp = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
    return GenerateSummaryResponse(
        shift_id="shift-minimal",
        status="draft",
        generated_at=stamp,
        results=[
            PatientSummaryResult(patient_id="pt_min", success=True, summary=None, error=None),
        ],
    )


CMS_BODY = {
    "request_id": "cms-handover-20260902143012",
    "context_type": "nursing_handover",
    "purpose": "shift_handover",
    "detail_level": "standard",
    "encounter_id": "ENC-2026-004471",
    "patient_data": {
        "allergies": [{"allergy_description": "Penicillin", "allergy_type_description": "Drug"}],
        "warnings": [{"virus_description": "MRSA colonisation", "type": "Infection Control"}],
        "last_hospital_course": "Admitted with pneumonia.",
        "past_medical_history": [
            {"record_type": "Family History", "record_description": "Type: Heart Disease"}
        ],
        "diagnosis": [
            {
                "diagnosis_type": "Principal",
                "diagnosis_code": "J18.9",
                "diagnosis_description": "Pneumonia, unspecified organism",
            }
        ],
        "vital_signs": {
            "respiratory_rate": "18",
            "bp_diastolic": "76",
            "bp_systolic": "128",
            "pain_score": "3",
            "pulse_rate": "88",
            "spo2_pct": "95",
            "temperature_c": "37.4",
        },
        "pending_operations": [
            {"operation_name": "Bronchoscopy", "requested_date": "2026-09-04T09:00:00"}
        ],
    },
}


def test_generate_without_any_headers(client):
    with patch(
        "app.routes.summary.generate_shift_summaries",
        new=AsyncMock(return_value=_fake_response()),
    ):
        response = client.post(
            "/summary/generate",
            content=json.dumps(MINIMAL_BODY),
            headers={},
        )
    assert response.status_code == 200
    assert response.json()["shift_id"] == "shift-minimal"


def test_health_without_headers(client):
    response = client.get("/health", headers={})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_generate_accepts_cms_patient_data(client):
    captured = {}

    async def fake_generate(req):
        captured["req"] = req
        return _fake_response()

    with patch("app.routes.summary.generate_shift_summaries", new=fake_generate):
        response = client.post(
            "/summary/generate",
            content=json.dumps(CMS_BODY),
            headers={},
        )
    assert response.status_code == 200
    req = captured["req"]
    assert req.request_id == "cms-handover-20260902143012"
    assert req.encounter_id == "ENC-2026-004471"
    patient = req.patient
    assert patient.patient_id == "ENC-2026-004471"
    assert patient.allergies[0].name == "Penicillin"
    assert patient.warnings[0].text == "MRSA colonisation"
    assert patient.pending_procedures[0].name == "Bronchoscopy"
    assert "J18.9" in patient.diagnosis


def test_generate_rejects_two_patients(client):
    body = {
        "shift_id": "shift-x",
        "nurse_id": "nurse_001",
        "patients": [
            {"patient_id": "pt_a", "name": "A"},
            {"patient_id": "pt_b", "name": "B"},
        ],
    }
    response = client.post(
        "/summary/generate",
        content=json.dumps(body),
        headers={},
    )
    assert response.status_code == 422

