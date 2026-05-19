"""Integration tests for REST API endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app
from app.api.routes import discharge_planner_service
from tests.fixtures.sample_data import (
    SAMPLE_REQUEST_MINIMAL,
    SAMPLE_REQUEST_FULL,
)


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_discharge_plan():
    """Mock discharge plan from AI."""
    return {
        "readiness_status": "needs_review",
        "readiness_reason": "Unresolved blockers remain.",
        "blockers": [
            {"category": "pending_test", "title": "Blood culture pending", "reason": "Test not complete"},
        ],
        "medication_reconciliation_concerns": ["Verify Prednisone"],
        "follow_up_considerations": ["Schedule pulmonology"],
        "draft_discharge_summary": "Patient admitted with pneumonia.",
        "disclaimer": "This output supports discharge planning and does not replace clinician judgment.",
    }


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
        assert data["service"] == "smart-discharge-planner"
        assert "provider" in data
        assert data["provider"] == "openai"


class TestPlanDischargeEndpoint:
    """Test plan-discharge endpoint."""
    
    def test_plan_discharge_success(self, client, mock_discharge_plan):
        """Test successful discharge planning."""
        with patch.object(discharge_planner_service, 'ai_client', MagicMock()) as mock_ai:
            mock_ai.plan_discharge.return_value = mock_discharge_plan
        
            request_data = {
                "request_id": "req-001",
                "patient_context": {
                    "patient_id": "P-1001",
                    "primary_diagnosis": "Pneumonia",
                },
                "clinical_data": {},
                "operational_data": {},
            }
            
            response = client.post("/api/v1/plan-discharge", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "discharge_plan" in data
        assert data["discharge_plan"]["readiness_status"] == "needs_review"
        assert "blockers" in data["discharge_plan"]
        assert "request_id" in data
        assert "processing_metadata" in data
    
    def test_plan_discharge_missing_patient_context(self, client):
        """Test plan-discharge with missing patient_context."""
        request_data = {
            "clinical_data": {},
            "operational_data": {},
        }
        response = client.post("/api/v1/plan-discharge", json=request_data)
        assert response.status_code == 422
    
    def test_plan_discharge_missing_clinical_data(self, client):
        """Test plan-discharge with missing clinical_data."""
        request_data = {
            "patient_context": {"patient_id": "P-1", "primary_diagnosis": "Dx"},
            "operational_data": {},
        }
        response = client.post("/api/v1/plan-discharge", json=request_data)
        assert response.status_code == 422
    
    def test_plan_discharge_api_error(self, client):
        """Test plan-discharge with API error."""
        with patch.object(discharge_planner_service, 'ai_client', MagicMock()) as mock_ai:
            mock_ai.plan_discharge.side_effect = ValueError("API error")
            request_data = {
                "patient_context": {"patient_id": "P-1", "primary_diagnosis": "Dx"},
                "clinical_data": {},
                "operational_data": {},
            }
            response = client.post("/api/v1/plan-discharge", json=request_data)
        assert response.status_code == 400
    
    def test_plan_discharge_without_request_id(self, client, mock_discharge_plan):
        """Test plan-discharge without request_id (should auto-generate)."""
        with patch.object(discharge_planner_service, 'ai_client', MagicMock()) as mock_ai:
            mock_ai.plan_discharge.return_value = mock_discharge_plan
            request_data = {
                "patient_context": {"patient_id": "P-1", "primary_diagnosis": "Dx"},
                "clinical_data": {},
                "operational_data": {},
            }
            response = client.post("/api/v1/plan-discharge", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert data["request_id"] is not None


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
        assert "/api/v1/plan-discharge" in schema["paths"]
        assert "/api/v1/health" in schema["paths"]
