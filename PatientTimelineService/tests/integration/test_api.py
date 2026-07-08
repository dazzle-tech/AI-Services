"""Integration tests for REST API endpoints."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.routes import timeline_service
from main import app
from tests.fixtures.sample_data import SAMPLE_TIMELINE_EVENTS


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
        assert data["service"] == "patient-timeline"
        assert "provider" in data
        assert data["provider"] == "openai"


class TestGenerateTimelineEndpoint:
    """Test timeline endpoint (canonical flat request shape)."""

    def test_generate_timeline_success(self, client):
        """Test successful timeline generation."""
        with patch.object(
            timeline_service.ai_client,
            "generate_timeline",
            return_value=SAMPLE_TIMELINE_EVENTS
        ):
            request_data = {
                "request_id": "test-001",
                "patient_context": {
                    "age": "58 years",
                    "sex": "Male"
                },
                "diagnoses": [
                    {
                        "name": "Hypertension",
                        "date": "2021-03-10"
                    }
                ]
            }

            response = client.post("/api/v1/generate-timeline", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "timeline" in data
        assert "request_id" in data
        assert "processing_metadata" in data
        assert isinstance(data["timeline"], list)
        assert len(data["timeline"]) == 2

    def test_generate_timeline_missing_required_fields(self, client):
        """Test timeline generation with an invalid entry (diagnosis missing name)."""
        request_data = {
            "patient_context": {
                "age": "58 years"
            },
            "diagnoses": [
                {"date": "2021-03-10"}
            ]
        }

        response = client.post("/api/v1/generate-timeline", json=request_data)
        assert response.status_code == 422

    def test_generate_timeline_complete_data(self, client):
        """Test timeline generation with complete patient data, including lab_results and medications."""
        with patch.object(
            timeline_service.ai_client,
            "generate_timeline",
            return_value=SAMPLE_TIMELINE_EVENTS
        ):
            request_data = {
                "request_id": "bce95302-cfc9-4a76-9cb0-e5013ed2710b",
                "patient_context": {
                    "age": "10 Years 9 Months 7 Days",
                    "sex": "FEMALE",
                    "known_conditions": []
                },
                "diagnoses": [
                    {
                        "name": "Type 2 Diabetes",
                        "date": "2022-05-01"
                    }
                ],
                "lab_results": [
                    {
                        "name": "CBC1",
                        "value": "25.00",
                        "unit": "Ratio",
                        "reference_range": "5.0 - 10.0",
                        "flag": "critical_upper",
                        "timestamp": "2026-04-20T13:31:06.908451Z"
                    }
                ],
                "medications": [
                    {
                        "name": "nexium",
                        "start_date": "2026-07-07T21:00:00.000Z",
                        "end_date": None
                    }
                ],
                "notes": [
                    {
                        "date": "2026-03-12",
                        "author": "Dr. Smith",
                        "type": "admission_note",
                        "text": "Patient admitted with chest pain."
                    }
                ]
            }

            response = client.post("/api/v1/generate-timeline", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "timeline" in data

    def test_generate_timeline_without_request_id(self, client):
        """Test timeline generation without request_id."""
        with patch.object(
            timeline_service.ai_client,
            "generate_timeline",
            return_value=SAMPLE_TIMELINE_EVENTS
        ):
            request_data = {
                "patient_context": {
                    "age": "58 years",
                    "sex": "Male"
                }
            }

            response = client.post("/api/v1/generate-timeline", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert data["request_id"] is not None

    def test_generate_timeline_api_error(self, client):
        """Test timeline generation with AI error."""
        with patch.object(
            timeline_service.ai_client,
            "generate_timeline",
            side_effect=ValueError("API error")
        ):
            request_data = {
                "patient_context": {
                    "age": "58 years",
                    "sex": "Male"
                }
            }

            response = client.post("/api/v1/generate-timeline", json=request_data)

        assert response.status_code == 400

    def test_generate_timeline_legacy_nested_shape(self, client):
        """Test that the legacy {"patient_data": {...}} request shape is still accepted."""
        with patch.object(
            timeline_service.ai_client,
            "generate_timeline",
            return_value=SAMPLE_TIMELINE_EVENTS
        ):
            request_data = {
                "request_id": "test-legacy",
                "patient_data": {
                    "patient_id": "12345",
                    "demographics": {
                        "age": "58 years",
                        "gender": "Male"
                    },
                    "diagnoses": [
                        {
                            "name": "Hypertension",
                            "date": "2021-03-10"
                        }
                    ]
                }
            }

            response = client.post("/api/v1/generate-timeline", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == "test-legacy"
        assert len(data["timeline"]) == 2


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
        assert "/api/v1/generate-timeline" in schema["paths"]
        assert "/api/v1/health" in schema["paths"]
