"""Integration tests for service layer."""
import pytest
from unittest.mock import patch, MagicMock
from app.services.lab_interpreter_service import LabInterpreterService
from app.models.schemas import LabInterpretationRequest
from tests.fixtures.sample_data import (
    SAMPLE_REQUEST_MINIMAL,
    SAMPLE_REQUEST_FULL,
    SAMPLE_LAB_MINIMAL,
)


class TestLabInterpreterService:
    """Test LabInterpreterService."""

    @patch("app.services.lab_interpreter_service.AIClient")
    def test_process_request_success(self, mock_ai_client):
        """Test successful request processing."""
        mock_client_instance = MagicMock()
        mock_client_instance.interpret_labs.return_value = {
            "severity": "moderate",
            "key_findings": ["WBC is normal"],
            "patterns": [],
            "trends": [],
            "follow_up_considerations": [],
            "disclaimer": "This output is interpretation support and not a diagnosis.",
        }
        mock_ai_client.return_value = mock_client_instance

        service = LabInterpreterService()
        response = service.process_request(SAMPLE_REQUEST_MINIMAL)

        assert response.request_id == "req-lab-001"
        assert response.interpretation is not None
        assert "WBC" in str(response.interpretation.key_findings)
        assert response.processing_metadata is not None
        assert "model" in response.processing_metadata
        assert "timestamp" in response.processing_metadata
        assert "lab_result_count" in response.processing_metadata

    @patch("app.services.lab_interpreter_service.AIClient")
    def test_process_request_auto_generates_id(self, mock_ai_client):
        """Test that request_id is auto-generated if not provided."""
        mock_client_instance = MagicMock()
        mock_client_instance.interpret_labs.return_value = {
            "severity": "low",
            "key_findings": [],
            "patterns": [],
            "trends": [],
            "follow_up_considerations": [],
            "disclaimer": "This output is interpretation support and not a diagnosis.",
        }
        mock_ai_client.return_value = mock_client_instance

        request = LabInterpretationRequest(lab_results=SAMPLE_LAB_MINIMAL)
        service = LabInterpreterService()
        response = service.process_request(request)

        assert response.request_id is not None
        assert response.request_id.startswith("req_")

    @patch("app.services.lab_interpreter_service.AIClient")
    def test_process_request_with_full_data(self, mock_ai_client):
        """Test processing request with full data including historical."""
        mock_client_instance = MagicMock()
        mock_client_instance.interpret_labs.return_value = {
            "severity": "high",
            "key_findings": ["WBC elevated", "CRP markedly elevated"],
            "patterns": [
                {"label": "possible_infection", "reason": "WBC and CRP suggest inflammation"},
            ],
            "trends": [
                {"lab_name": "Creatinine", "direction": "rising", "summary": "Increased from 1.0 to 1.8"},
            ],
            "follow_up_considerations": ["Repeat lactate", "Review cultures"],
            "disclaimer": "This output is interpretation support and not a diagnosis.",
        }
        mock_ai_client.return_value = mock_client_instance

        service = LabInterpreterService()
        response = service.process_request(SAMPLE_REQUEST_FULL)

        assert response.request_id == "req-lab-001"
        assert len(response.interpretation.key_findings) > 0
        assert len(response.interpretation.patterns) > 0
        assert len(response.interpretation.trends) > 0
        assert response.processing_metadata["lab_result_count"] == 2
        assert response.processing_metadata["trend_count"] == 1

    @patch("app.services.lab_interpreter_service.AIClient")
    def test_process_request_api_error(self, mock_ai_client):
        """Test handling of API errors."""
        mock_client_instance = MagicMock()
        mock_client_instance.interpret_labs.side_effect = ValueError("OpenAI API error")
        mock_ai_client.return_value = mock_client_instance

        service = LabInterpreterService()

        with pytest.raises(ValueError, match="OpenAI API error"):
            service.process_request(SAMPLE_REQUEST_MINIMAL)

    @patch("app.services.lab_interpreter_service.AIClient")
    def test_metadata_includes_lab_count_and_trend_count(self, mock_ai_client):
        """Test that metadata includes lab_result_count and trend_count."""
        mock_client_instance = MagicMock()
        mock_client_instance.interpret_labs.return_value = {
            "severity": "moderate",
            "key_findings": [],
            "patterns": [],
            "trends": [{"lab_name": "Cr", "direction": "rising", "summary": "Up"}],
            "follow_up_considerations": [],
            "disclaimer": "This output is interpretation support and not a diagnosis.",
        }
        mock_ai_client.return_value = mock_client_instance

        service = LabInterpreterService()
        response = service.process_request(SAMPLE_REQUEST_FULL)

        assert response.processing_metadata["lab_result_count"] == 2
        assert response.processing_metadata["trend_count"] == 1
        assert response.processing_metadata["provider"] == "openai"
