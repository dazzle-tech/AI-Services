"""Tests for SepsisSentinel API routes."""
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Ensure OPENAI_API_KEY is set before importing the app so config
# does not fail during test collection.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-testing-only")

from main import app  # noqa: E402


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


# ------------------------------------------------------------------
# Root endpoint
# ------------------------------------------------------------------

def test_root_returns_200(client):
    """GET / should return 200 with service info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data
    assert "docs" in data


# ------------------------------------------------------------------
# Health endpoint
# ------------------------------------------------------------------

def test_health_returns_200(client):
    """GET /api/v1/health should return 200 with status fields."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "openai_configured" in data


# ------------------------------------------------------------------
# Patients list endpoint
# ------------------------------------------------------------------

def test_patients_returns_200(client):
    """GET /api/v1/patients should return a list of patients."""
    response = client.get("/api/v1/patients")
    assert response.status_code == 200
    data = response.json()
    assert "patients" in data
    assert isinstance(data["patients"], list)
    assert len(data["patients"]) == 3


def test_patients_have_required_fields(client):
    """Each patient in the list should have id, name, and admission_reason."""
    response = client.get("/api/v1/patients")
    data = response.json()
    for patient in data["patients"]:
        assert "patient_id" in patient
        assert "name" in patient
        assert "admission_reason" in patient


def test_patient_detail_returns_200(client):
    """GET /api/v1/patients/{id} should return the full patient payload."""
    response = client.get("/api/v1/patients/1")
    assert response.status_code == 200
    data = response.json()
    assert data["patient_id"] == 1
    assert "patient_data" in data
    assert "patient_info" in data["patient_data"]
    assert "hourly_data" in data["patient_data"]


# ------------------------------------------------------------------
# Analyze endpoint -- validation
# ------------------------------------------------------------------

def test_analyze_rejects_empty_body(client):
    """POST /api/v1/analyze with empty body should return 400."""
    response = client.post("/api/v1/analyze", json={})
    assert response.status_code == 400


def test_analyze_rejects_invalid_patient_id(client):
    """POST /api/v1/analyze with out-of-range patient_id should return 422."""
    response = client.post("/api/v1/analyze", json={"patient_id": 99})
    assert response.status_code == 422


def test_analyze_rejects_both_fields(client):
    """POST /api/v1/analyze with both patient_id and patient_data should 400."""
    response = client.post(
        "/api/v1/analyze",
        json={"patient_id": 1, "patient_data": {"foo": "bar"}},
    )
    assert response.status_code == 400


def test_custom_analyses_rejects_empty_body(client):
    """POST /api/v1/analyses with empty body should return 422."""
    response = client.post("/api/v1/analyses", json={})
    assert response.status_code == 422


# ------------------------------------------------------------------
# Analyze endpoint -- mocked AI call
# ------------------------------------------------------------------

def test_create_sample_analysis_with_valid_patient_id(client):
    """POST /api/v1/patients/{id}/analyses should return 201."""
    mock_result = {
        "patient_snapshot": {"name": "Test"},
        "status_summary": {"overall_condition": "stable"},
    }

    with patch(
        "app.services.sepsis_service.SepsisAIClient.analyze",
        return_value=mock_result,
    ):
        response = client.post("/api/v1/patients/1/analyses")

    assert response.status_code == 201
    data = response.json()
    assert "analysis" in data
    assert data["patient_id"] == 1
    assert data["source"] == "sample"


def test_create_custom_analysis_with_patient_data(client):
    """POST /api/v1/analyses should return 201 when AI is mocked."""
    mock_result = {
        "patient_snapshot": {"name": "Custom Test"},
        "status_summary": {"overall_condition": "watch"},
    }
    payload = {
        "patient_data": {
            "patient_info": {
                "name": "Jane Doe",
                "admission_reason": "Observation",
            },
            "hourly_data": [],
        }
    }

    with patch(
        "app.services.sepsis_service.SepsisAIClient.analyze",
        return_value=mock_result,
    ):
        response = client.post("/api/v1/analyses", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert "analysis" in data
    assert data["patient_id"] is None
    assert data["source"] == "custom"


def test_create_custom_analysis_normalizes_flat_llm_output(client):
    """Flat LLM output should be normalized before returning to the client."""
    mock_result = {
        "patient_name": "Sonsoabd",
        "age": 26,
        "gender": "FEMALE",
        "status_summary": "Guarded condition",
        "patient_vitals": {},
        "current_labs": {},
    }
    payload = {
        "patient_data": {
            "patient_info": {
                "name": "Sonsoabd",
                "age": 26,
                "gender": "FEMALE",
                "comorbidities": ["Abscess of bursa (M71.0)"],
            },
            "hourly_data": [],
        }
    }

    with patch(
        "app.services.sepsis_service.SepsisAIClient.analyze",
        return_value=mock_result,
    ):
        response = client.post("/api/v1/analyses", json=payload)

    assert response.status_code == 201
    analysis = response.json()["analysis"]
    assert "patient_snapshot" in analysis
    assert analysis["patient_snapshot"]["name"] == "Sonsoabd"
    assert "patient_name" not in analysis
    assert isinstance(analysis["status_summary"], dict)


def test_legacy_analyze_with_valid_patient_id(client):
    """POST /api/v1/analyze should remain available for compatibility."""
    mock_result = {
        "patient_snapshot": {"name": "Test"},
        "status_summary": {"overall_condition": "stable"},
    }

    with patch(
        "app.services.sepsis_service.SepsisAIClient.analyze",
        return_value=mock_result,
    ):
        response = client.post(
            "/api/v1/analyze",
            json={"patient_id": 1},
        )

    assert response.status_code == 200
    data = response.json()
    assert "analysis" in data
    assert data["patient_id"] == 1
    assert data["source"] == "sample"
