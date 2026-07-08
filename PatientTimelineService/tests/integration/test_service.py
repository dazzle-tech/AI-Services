"""Integration tests for service layer."""
import os
from unittest.mock import MagicMock, patch

import pytest

from app.models.schemas import TimelineEvent, TimelineRequest
from app.services.timeline_service import TimelineService
from tests.fixtures.sample_data import SAMPLE_REQUEST_COMPLETE, SAMPLE_REQUEST_MINIMAL

TEST_MODEL = os.getenv("OPENAI_MODEL", "")


class TestTimelineService:
    """Test TimelineService."""

    @patch("app.services.timeline_service.AIClient")
    def test_process_request_success(self, mock_ai_client):
        """Test successful request processing."""
        mock_client_instance = MagicMock()
        mock_client_instance.generate_timeline.return_value = [
            TimelineEvent(
                date="2021-03-10",
                event_type="diagnosis",
                title="Hypertension diagnosed",
                description="Hypertension documented.",
                clinical_importance="medium",
                source="diagnoses"
            )
        ]
        mock_ai_client.return_value = mock_client_instance

        service = TimelineService()
        response = service.process_request(SAMPLE_REQUEST_MINIMAL)

        assert response.request_id == "test-001"
        assert len(response.timeline) == 1
        assert response.timeline[0].event_type == "diagnosis"
        assert response.processing_metadata.model == TEST_MODEL
        assert response.processing_metadata.timeline_event_count == 1

    @patch("app.services.timeline_service.AIClient")
    def test_process_request_auto_generates_id(self, mock_ai_client):
        """Test that request_id is auto-generated if not provided."""
        mock_client_instance = MagicMock()
        mock_client_instance.generate_timeline.return_value = []
        mock_ai_client.return_value = mock_client_instance

        request = TimelineRequest(
            patient_context=SAMPLE_REQUEST_MINIMAL.patient_context,
            diagnoses=SAMPLE_REQUEST_MINIMAL.diagnoses,
        )
        service = TimelineService()
        response = service.process_request(request)

        assert response.request_id is not None
        assert response.request_id.startswith("req_")

    @patch("app.services.timeline_service.AIClient")
    def test_process_request_deduplicates_and_sorts(self, mock_ai_client):
        """Test duplicate merging and chronological sorting."""
        mock_client_instance = MagicMock()
        mock_client_instance.generate_timeline.return_value = [
            TimelineEvent(
                date="2026-03-12",
                event_type="admission",
                title="Admitted with chest pain",
                description="Hospital admission due to chest pain.",
                clinical_importance="high",
                source="encounters"
            ),
            TimelineEvent(
                date="2020-02-15",
                event_type="procedure",
                title="Coronary angiography performed",
                description="Completed coronary angiography procedure.",
                clinical_importance="high",
                source="procedures"
            ),
            TimelineEvent(
                date="2026-03-12",
                event_type="admission",
                title="Admitted with chest pain",
                description="Patient admitted with chest pain and shortness of breath.",
                clinical_importance="high",
                source="notes"
            )
        ]
        mock_ai_client.return_value = mock_client_instance

        service = TimelineService()
        response = service.process_request(SAMPLE_REQUEST_COMPLETE)

        assert len(response.timeline) == 2
        assert response.timeline[0].date == "2020-02-15"
        assert response.timeline[1].source == "encounters, notes"
        assert response.processing_metadata.timeline_event_count == 2

    @patch("app.services.timeline_service.AIClient")
    def test_process_request_api_error(self, mock_ai_client):
        """Test handling of AI errors."""
        mock_client_instance = MagicMock()
        mock_client_instance.generate_timeline.side_effect = ValueError("OpenAI API error")
        mock_ai_client.return_value = mock_client_instance

        service = TimelineService()

        with pytest.raises(ValueError, match="OpenAI API error"):
            service.process_request(SAMPLE_REQUEST_MINIMAL)

    @patch("app.services.timeline_service.AIClient")
    def test_process_request_accepts_vital_events(self, mock_ai_client):
        """Test that vital events are accepted after normalization."""
        mock_client_instance = MagicMock()
        mock_client_instance.generate_timeline.return_value = [
            TimelineEvent(
                date="2026-03-12",
                event_type="vital",
                title="Blood pressure elevated",
                description="BP recorded at 160/100.",
                clinical_importance="medium",
                source="vitals"
            )
        ]
        mock_ai_client.return_value = mock_client_instance

        service = TimelineService()
        response = service.process_request(SAMPLE_REQUEST_COMPLETE)

        assert len(response.timeline) == 1
        assert response.timeline[0].event_type == "vital"
        assert response.timeline[0].source == "vitals"
