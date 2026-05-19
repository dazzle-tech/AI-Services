"""Integration tests for REST API endpoints."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.models.schemas import AlertResponse
from main import app
from tests.fixtures.sample_data import SAMPLE_ALERT


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_endpoint(self, client):
        """Test root endpoint returns service info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "model" in data
        assert "docs" in data


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_endpoint(self, client):
        """Test health endpoint."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert data["service"] == "specialist-alert"
        assert "provider" in data
        assert data["provider"] == "openai"


class TestGenerateAlertsEndpoint:
    """Test generate-alerts endpoint."""

    @patch("app.api.routes.alert_service.process_request")
    def test_generate_alerts_success(self, mock_process_request, client):
        """Test successful alert generation."""
        mock_process_request.return_value = AlertResponse(
            request_id="test-001",
            alerts=[SAMPLE_ALERT],
            summary="Clinical alerts generated successfully.",
            processing_metadata={"alert_count": 1},
        )

        request_data = {
            "request_id": "test-001",
            "patient_record": {
                "patient_id": "P-1001",
                "demographics": {"age": 58, "sex": "male"},
            },
        }

        response = client.post("/api/v1/generate-alerts", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert "request_id" in data
        assert "processing_metadata" in data
        assert isinstance(data["alerts"], list)
        assert data["alerts"][0]["category"] == "urgent_escalation"

    def test_generate_alerts_missing_required_fields(self, client):
        """Test alerts endpoint with missing required fields."""
        request_data = {"patient_record": {"demographics": {"age": 58}}}

        response = client.post("/api/v1/generate-alerts", json=request_data)
        assert response.status_code == 422

    def test_generate_alerts_empty_patient_id(self, client):
        """Test alerts endpoint with empty patient_id."""
        request_data = {"patient_record": {"patient_id": ""}}

        response = client.post("/api/v1/generate-alerts", json=request_data)
        assert response.status_code == 422

    @patch("app.api.routes.alert_service.process_request")
    def test_generate_alerts_without_request_id(self, mock_process_request, client):
        """Test alert generation without request_id."""
        mock_process_request.return_value = AlertResponse(
            request_id="req_20260331_095500",
            alerts=[SAMPLE_ALERT],
            summary="Clinical alerts generated successfully.",
            processing_metadata={"alert_count": 1},
        )

        request_data = {"patient_record": {"patient_id": "P-1001"}}

        response = client.post("/api/v1/generate-alerts", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert data["request_id"] is not None

    @patch("app.api.routes.alert_service.process_request")
    def test_generate_alerts_malformed_ai_output_returns_400(self, mock_process_request, client):
        """Test malformed AI output handling through the API."""
        mock_process_request.side_effect = ValueError("Malformed alert JSON after 3 attempts")

        request_data = {"patient_record": {"patient_id": "P-1001"}}

        response = client.post("/api/v1/generate-alerts", json=request_data)
        assert response.status_code == 400
        assert "Malformed alert JSON" in response.json()["detail"]


class TestAPIDocumentation:
    """Test API documentation endpoints."""

    def test_docs_endpoint(self, client):
        """Test that Swagger docs are available."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_endpoint(self, client):
        """Test that ReDoc is available."""
        response = client.get("/redoc")
        assert response.status_code == 200

    def test_openapi_schema(self, client):
        """Test OpenAPI schema endpoint."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema
        assert "/api/v1/generate-alerts" in schema["paths"]
        assert "/api/v1/health" in schema["paths"]
