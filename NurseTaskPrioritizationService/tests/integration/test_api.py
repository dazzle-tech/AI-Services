"""Integration tests for REST API endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app
from app.api.routes import prioritization_service
from tests.fixtures.sample_data import (
    SAMPLE_REQUEST_MINIMAL,
    SAMPLE_REQUEST_FULL,
)


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_prioritization_response():
    """Mock AI prioritization response."""
    return [
        {
            "rank": 1,
            "patient_id": "P-1001",
            "room": "101",
            "task_id": "TASK-1",
            "task_type": "clinical_reassessment",
            "title": "Reassess oxygen therapy",
            "reason": "Oxygen saturation is 88%.",
            "urgency": "critical",
            "recommended_timeframe": "immediate",
            "source_signals": ["oxygen_saturation=88%"]
        }
    ]


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
        assert data["service"] == "nurse-task-prioritization"
        assert "provider" in data
        assert data["provider"] == "openai"


class TestPrioritizeTasksEndpoint:
    """Test prioritize-tasks endpoint."""

    @patch.object(prioritization_service, 'ai_client')
    def test_prioritize_success(self, mock_ai_client, client, mock_prioritization_response):
        """Test successful task prioritization."""
        mock_ai_client.prioritize_tasks.return_value = mock_prioritization_response

        request_data = SAMPLE_REQUEST_FULL.model_dump()
        response = client.post("/api/v1/prioritize-tasks", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "prioritized_tasks" in data
        assert "request_id" in data
        assert "processing_metadata" in data
        assert isinstance(data["prioritized_tasks"], list)
        assert len(data["prioritized_tasks"]) > 0

    def test_prioritize_missing_required_fields(self, client):
        """Test prioritize with missing required fields."""
        request_data = {
            "unit_context": {"unit_name": "Ward", "shift": "day", "generated_at": "2026-03-16T09:00:00Z"}
            # Missing nurse_context and patients
        }
        response = client.post("/api/v1/prioritize-tasks", json=request_data)
        assert response.status_code == 422

    def test_prioritize_invalid_payload(self, client):
        """Test prioritize with invalid payload."""
        request_data = {"invalid": "payload"}
        response = client.post("/api/v1/prioritize-tasks", json=request_data)
        assert response.status_code in (400, 422)

    @patch.object(prioritization_service, 'ai_client')
    def test_prioritize_without_request_id(self, mock_ai_client, client, mock_prioritization_response):
        """Test prioritize without request_id (should auto-generate)."""
        mock_ai_client.prioritize_tasks.return_value = mock_prioritization_response

        request_data = SAMPLE_REQUEST_FULL.model_dump()
        del request_data["request_id"]
        response = client.post("/api/v1/prioritize-tasks", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert data["request_id"] is not None

    @patch.object(prioritization_service, 'ai_client')
    def test_prioritize_api_error(self, mock_ai_client, client):
        """Test prioritize with API error."""
        mock_ai_client.prioritize_tasks.side_effect = ValueError("API error")

        request_data = SAMPLE_REQUEST_FULL.model_dump()
        response = client.post("/api/v1/prioritize-tasks", json=request_data)
        assert response.status_code == 400


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
        assert "/api/v1/prioritize-tasks" in schema["paths"]
        assert "/api/v1/health" in schema["paths"]
