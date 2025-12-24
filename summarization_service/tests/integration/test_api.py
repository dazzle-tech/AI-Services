"""Integration tests for REST API endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app
from app.models.schemas import SummaryResponse
from tests.fixtures.sample_data import (
    SAMPLE_REQUEST_MINIMAL,
    SAMPLE_REQUEST_COMPLETE,
    SAMPLE_PATIENT_MINIMAL
)


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "A 45-year-old male with Type 2 Diabetes. Patient presents with symptoms and is currently on medications."
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 150
    mock_response.usage.completion_tokens = 50
    mock_response.usage.total_tokens = 200
    return mock_response


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
        assert data["service"] == "clinical-summary"
        assert "provider" in data
        assert data["provider"] == "openai"


class TestSummarizeEndpoint:
    """Test summarize endpoint."""
    
    @patch('app.services.summarization_service.AIClient')
    def test_summarize_success(self, mock_ai_client, client, mock_openai_response):
        """Test successful summary generation."""
        # Mock AI client
        mock_client_instance = MagicMock()
        mock_client_instance.generate_summary.return_value = "A 45-year-old male with Type 2 Diabetes."
        mock_ai_client.return_value = mock_client_instance
        
        # Make request
        request_data = {
            "request_id": "test-001",
            "patient_data": {
                "Age": "45 years",
                "Gender": "Male",
                "Diagnosis": "Type 2 Diabetes"
            }
        }
        
        response = client.post("/api/v1/summarize", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "ClinicalSummary" in data
        assert "request_id" in data
        assert "processing_metadata" in data
        assert isinstance(data["ClinicalSummary"], str)
        assert len(data["ClinicalSummary"]) > 0
    
    def test_summarize_missing_required_fields(self, client):
        """Test summarize with missing required fields."""
        request_data = {
            "patient_data": {
                "Age": "45 years",
                # Missing Gender and Diagnosis
            }
        }
        
        response = client.post("/api/v1/summarize", json=request_data)
        assert response.status_code == 422  # Validation error
    
    def test_summarize_empty_age(self, client):
        """Test summarize with empty age."""
        request_data = {
            "patient_data": {
                "Age": "",
                "Gender": "Male",
                "Diagnosis": "Diabetes"
            }
        }
        
        response = client.post("/api/v1/summarize", json=request_data)
        assert response.status_code == 422  # Validation error
    
    def test_summarize_complete_data(self, client, mock_openai_response):
        """Test summarize with complete patient data."""
        with patch('app.services.summarization_service.AIClient') as mock_ai:
            mock_client_instance = MagicMock()
            mock_client_instance.generate_summary.return_value = "A 58-year-old male with STEMI."
            mock_ai.return_value = mock_client_instance
            
            request_data = {
                "patient_data": {
                    "Age": "58 years",
                    "Gender": "Male",
                    "Diagnosis": "STEMI",
                    "Symptoms": ["Chest pain", "SOB"],
                    "Medications": ["Aspirin 325mg"],
                    "Allergies": ["Penicillin"],
                    "Vitals": {"BP": "140/90", "HR": "72"}
                }
            }
            
            response = client.post("/api/v1/summarize", json=request_data)
            assert response.status_code == 200
            data = response.json()
            assert "ClinicalSummary" in data
    
    def test_summarize_without_request_id(self, client, mock_openai_response):
        """Test summarize without request_id (should auto-generate)."""
        with patch('app.services.summarization_service.AIClient') as mock_ai:
            mock_client_instance = MagicMock()
            mock_client_instance.generate_summary.return_value = "Test summary"
            mock_ai.return_value = mock_client_instance
            
            request_data = {
                "patient_data": {
                    "Age": "45 years",
                    "Gender": "Male",
                    "Diagnosis": "Diabetes"
                }
            }
            
            response = client.post("/api/v1/summarize", json=request_data)
            assert response.status_code == 200
            data = response.json()
            # Request ID should be auto-generated
            assert "request_id" in data
            assert data["request_id"] is not None
    
    @patch('app.services.summarization_service.AIClient')
    def test_summarize_api_error(self, mock_ai_client, client):
        """Test summarize with API error."""
        # Mock AI client to raise error
        mock_client_instance = MagicMock()
        mock_client_instance.generate_summary.side_effect = ValueError("API error")
        mock_ai_client.return_value = mock_client_instance
        
        request_data = {
            "patient_data": {
                "Age": "45 years",
                "Gender": "Male",
                "Diagnosis": "Diabetes"
            }
        }
        
        response = client.post("/api/v1/summarize", json=request_data)
        assert response.status_code == 400  # Bad request due to validation error


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
        assert "/api/v1/summarize" in schema["paths"]
        assert "/api/v1/health" in schema["paths"]

