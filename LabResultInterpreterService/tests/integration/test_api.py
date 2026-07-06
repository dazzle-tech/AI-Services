"""Integration tests for REST API endpoints."""
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app
from app.models.schemas import LabInterpretationResponse
from tests.fixtures.sample_data import (
    SAMPLE_REQUEST_MINIMAL,
    SAMPLE_REQUEST_FULL,
    SAMPLE_LAB_MINIMAL,
)

TEST_MODEL = os.getenv("OPENAI_MODEL", "")


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_interpretation_response():
    """Mock interpretation response from AI client."""
    return {
        "severity": "high",
        "key_findings": ["WBC is elevated", "CRP is markedly elevated"],
        "patterns": [
            {"label": "possible_infection_or_inflammation", "reason": "WBC and CRP suggest infection."},
        ],
        "trends": [
            {"lab_name": "Creatinine", "direction": "rising", "summary": "Increased from 1.0 to 1.8."},
        ],
        "follow_up_considerations": ["Review cultures", "Repeat lactate"],
        "disclaimer": "This output is interpretation support and not a diagnosis.",
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
        assert "Lab Result Interpreter" in data["message"]


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_endpoint(self, client):
        """Test health endpoint."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert data["service"] == "lab-result-interpreter"
        assert "provider" in data
        assert data["provider"] == "openai"


class TestInterpretLabsEndpoint:
    """Test interpret-labs endpoint."""

    @patch("app.api.routes.lab_interpreter_service")
    def test_interpret_labs_success(self, mock_service, client, mock_interpretation_response):
        """Test successful lab interpretation."""
        from app.models.schemas import (
            LabInterpretationResponse,
            LabInterpretation,
            LabPattern,
            LabTrend,
        )
        mock_service.process_request.return_value = LabInterpretationResponse(
            request_id="req-lab-001",
            interpretation=LabInterpretation(
                severity=mock_interpretation_response["severity"],
                key_findings=mock_interpretation_response["key_findings"],
                patterns=[LabPattern(**p) for p in mock_interpretation_response["patterns"]],
                trends=[LabTrend(**t) for t in mock_interpretation_response["trends"]],
                follow_up_considerations=mock_interpretation_response["follow_up_considerations"],
                disclaimer=mock_interpretation_response["disclaimer"],
            ),
            summary="Lab interpretation generated successfully.",
            processing_metadata={"model": TEST_MODEL, "lab_result_count": 1, "trend_count": 1},
        )

        request_data = {
            "request_id": "req-lab-001",
            "lab_results": [
                {
                    "name": "WBC",
                    "value": "18.2",
                    "unit": "10^9/L",
                    "reference_range": "4.0-11.0",
                    "flag": "high",
                }
            ],
            "historical_lab_results": [],
        }

        response = client.post("/api/v1/interpret-labs", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "interpretation" in data
        assert "request_id" in data
        assert "processing_metadata" in data
        assert "key_findings" in data["interpretation"]
        assert "patterns" in data["interpretation"]
        assert "trends" in data["interpretation"]
        assert "follow_up_considerations" in data["interpretation"]
        assert "disclaimer" in data["interpretation"]
        assert len(data["interpretation"]["key_findings"]) > 0

    def test_interpret_labs_missing_lab_results(self, client):
        """Test interpret-labs with missing lab_results."""
        request_data = {
            "lab_results": [],
        }
        response = client.post("/api/v1/interpret-labs", json=request_data)
        assert response.status_code == 422

    def test_interpret_labs_invalid_payload(self, client):
        """Test interpret-labs with invalid payload (no lab_results key)."""
        request_data = {}
        response = client.post("/api/v1/interpret-labs", json=request_data)
        assert response.status_code in (400, 422)

    @patch("app.api.routes.lab_interpreter_service")
    def test_interpret_labs_full_example(self, mock_service, client, mock_interpretation_response):
        """Test interpret-labs with full example including patient context and historical."""
        from app.models.schemas import (
            LabInterpretationResponse,
            LabInterpretation,
            LabPattern,
            LabTrend,
        )
        mock_service.process_request.return_value = LabInterpretationResponse(
            request_id="req-lab-001",
            interpretation=LabInterpretation(
                severity=mock_interpretation_response["severity"],
                key_findings=mock_interpretation_response["key_findings"],
                patterns=[LabPattern(**p) for p in mock_interpretation_response["patterns"]],
                trends=[LabTrend(**t) for t in mock_interpretation_response["trends"]],
                follow_up_considerations=mock_interpretation_response["follow_up_considerations"],
                disclaimer=mock_interpretation_response["disclaimer"],
            ),
            summary="Lab interpretation generated successfully.",
            processing_metadata={"model": TEST_MODEL, "lab_result_count": 3, "trend_count": 1},
        )

        request_data = {
            "request_id": "req-lab-001",
            "patient_context": {
                "patient_id": "P-1001",
                "age": 58,
                "sex": "male",
                "known_conditions": ["Type 2 Diabetes", "Hypertension"],
                "medications": ["Metformin", "Lisinopril"],
                "clinical_context": "Admitted with fever and shortness of breath",
            },
            "lab_results": [
                {"name": "WBC", "value": "18.2", "unit": "10^9/L", "reference_range": "4.0-11.0", "flag": "high"},
                {"name": "CRP", "value": "145", "unit": "mg/L", "reference_range": "0-5", "flag": "high"},
                {"name": "Lactate", "value": "3.4", "unit": "mmol/L", "reference_range": "0.5-2.2", "flag": "high"},
            ],
            "historical_lab_results": [
                {"name": "Creatinine", "value": "1.0", "unit": "mg/dL", "flag": "normal"},
                {"name": "Creatinine", "value": "1.8", "unit": "mg/dL", "flag": "high"},
            ],
        }

        response = client.post("/api/v1/interpret-labs", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["interpretation"]["severity"] == "high"
        assert "interpretation" in data
        assert "key_findings" in data["interpretation"]

    @patch("app.api.routes.lab_interpreter_service")
    def test_interpret_labs_without_request_id(self, mock_service, client, mock_interpretation_response):
        """Test interpret-labs without request_id (should auto-generate)."""
        from app.models.schemas import (
            LabInterpretationResponse,
            LabInterpretation,
            LabPattern,
            LabTrend,
        )
        mock_service.process_request.return_value = LabInterpretationResponse(
            request_id="req_20260101_120000",
            interpretation=LabInterpretation(
                severity=mock_interpretation_response["severity"],
                key_findings=mock_interpretation_response["key_findings"],
                patterns=[LabPattern(**p) for p in mock_interpretation_response["patterns"]],
                trends=[LabTrend(**t) for t in mock_interpretation_response["trends"]],
                follow_up_considerations=mock_interpretation_response["follow_up_considerations"],
                disclaimer=mock_interpretation_response["disclaimer"],
            ),
            summary="Lab interpretation generated successfully.",
            processing_metadata={"model": TEST_MODEL, "lab_result_count": 1, "trend_count": 1},
        )

        request_data = {
            "lab_results": [
                {"name": "WBC", "value": "10.0", "flag": "normal"},
            ],
        }

        response = client.post("/api/v1/interpret-labs", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert data["request_id"] is not None

    @patch("app.api.routes.lab_interpreter_service")
    def test_interpret_labs_api_error(self, mock_service, client):
        """Test interpret-labs with API error."""
        mock_service.process_request.side_effect = ValueError("API error")

        request_data = {
            "lab_results": [
                {"name": "WBC", "value": "10.0"},
            ],
        }

        response = client.post("/api/v1/interpret-labs", json=request_data)
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
        assert "/api/v1/interpret-labs" in schema["paths"]
        assert "/api/v1/health" in schema["paths"]
