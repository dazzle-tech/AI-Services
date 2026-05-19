"""Integration tests for service layer."""
import pytest
from unittest.mock import patch, MagicMock
from app.services.prioritization_service import PrioritizationService
from app.models.schemas import TaskPrioritizationRequest
from tests.fixtures.sample_data import (
    SAMPLE_REQUEST_MINIMAL,
    SAMPLE_REQUEST_FULL,
    SAMPLE_REQUEST_NO_ID,
)


class TestPrioritizationService:
    """Test PrioritizationService."""

    @patch('app.services.prioritization_service.AIClient')
    def test_process_request_success(self, mock_ai_client):
        """Test successful request processing."""
        mock_client_instance = MagicMock()
        mock_client_instance.prioritize_tasks.return_value = [
            {
                "rank": 1,
                "patient_id": "P-1001",
                "room": "101",
                "task_id": "TASK-1",
                "task_type": "clinical_reassessment",
                "title": "Reassess oxygen",
                "reason": "SpO2 low",
                "urgency": "critical",
                "recommended_timeframe": "immediate",
                "source_signals": ["oxygen_saturation=88%"]
            }
        ]
        mock_ai_client.return_value = mock_client_instance

        service = PrioritizationService()
        response = service.process_request(SAMPLE_REQUEST_MINIMAL)

        assert response.request_id == "req-001"
        assert len(response.prioritized_tasks) == 1
        assert response.prioritized_tasks[0].rank == 1
        assert response.processing_metadata is not None
        assert "model" in response.processing_metadata
        assert "timestamp" in response.processing_metadata

    @patch('app.services.prioritization_service.AIClient')
    def test_process_request_auto_generates_id(self, mock_ai_client):
        """Test that request_id is auto-generated if not provided."""
        mock_client_instance = MagicMock()
        mock_client_instance.prioritize_tasks.return_value = []
        mock_ai_client.return_value = mock_client_instance

        service = PrioritizationService()
        response = service.process_request(SAMPLE_REQUEST_NO_ID)

        assert response.request_id is not None
        assert response.request_id.startswith("req_")

    @patch('app.services.prioritization_service.AIClient')
    def test_process_request_with_full_data(self, mock_ai_client):
        """Test processing request with complete patient data."""
        mock_client_instance = MagicMock()
        mock_client_instance.prioritize_tasks.return_value = [
            {"rank": 1, "patient_id": "P-1001", "room": "101", "task_id": "TASK-1",
             "task_type": "clinical_reassessment", "title": "Reassess oxygen",
             "reason": "SpO2 88%", "urgency": "critical",
             "recommended_timeframe": "immediate", "source_signals": []},
            {"rank": 2, "patient_id": "P-1001", "room": "101", "task_id": "MED-1",
             "task_type": "medication", "title": "Administer insulin",
             "reason": "Due soon", "urgency": "high",
             "recommended_timeframe": "within_10_minutes", "source_signals": []},
        ]
        mock_ai_client.return_value = mock_client_instance

        service = PrioritizationService()
        response = service.process_request(SAMPLE_REQUEST_FULL)

        assert response.request_id == "req-001"
        assert len(response.prioritized_tasks) == 2
        assert response.processing_metadata["patient_count"] == 1
        assert response.processing_metadata["task_count"] == 2

    @patch('app.services.prioritization_service.AIClient')
    def test_process_request_api_error(self, mock_ai_client):
        """Test handling of API errors."""
        mock_client_instance = MagicMock()
        mock_client_instance.prioritize_tasks.side_effect = ValueError("OpenAI API error")
        mock_ai_client.return_value = mock_client_instance

        service = PrioritizationService()

        with pytest.raises(ValueError, match="OpenAI API error|Task prioritization failed"):
            service.process_request(SAMPLE_REQUEST_MINIMAL)

    @patch('app.services.prioritization_service.AIClient')
    def test_metadata_includes_counts(self, mock_ai_client):
        """Test that metadata includes patient_count and task_count."""
        mock_client_instance = MagicMock()
        mock_client_instance.prioritize_tasks.return_value = [
            {"rank": 1, "patient_id": "P-1001", "room": "101", "task_id": "TASK-1",
             "task_type": "nursing_task", "title": "Task 1", "reason": "Reason",
             "urgency": "medium", "recommended_timeframe": "as_able", "source_signals": []}
        ]
        mock_ai_client.return_value = mock_client_instance

        service = PrioritizationService()
        response = service.process_request(SAMPLE_REQUEST_FULL)

        assert response.processing_metadata["patient_count"] == 1
        assert response.processing_metadata["task_count"] == 1
        assert response.processing_metadata["provider"] == "openai"
