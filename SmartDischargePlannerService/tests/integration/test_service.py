"""Integration tests for service layer."""
import pytest
from unittest.mock import patch, MagicMock
from app.services.discharge_planner_service import DischargePlannerService
from app.models.schemas import DischargePlanningRequest
from tests.fixtures.sample_data import SAMPLE_REQUEST_MINIMAL, SAMPLE_REQUEST_FULL


class TestDischargePlannerService:
    """Test DischargePlannerService."""
    
    @patch('app.services.discharge_planner_service.AIClient')
    def test_process_request_success(self, mock_ai_client):
        """Test successful request processing."""
        mock_plan = {
            "readiness_status": "needs_review",
            "readiness_reason": "Blockers remain.",
            "blockers": [{"category": "pending_test", "title": "Test pending", "reason": "..."}],
            "medication_reconciliation_concerns": [],
            "follow_up_considerations": ["Schedule follow-up"],
            "draft_discharge_summary": "Patient admitted with pneumonia.",
            "disclaimer": "This output supports discharge planning and does not replace clinician judgment.",
        }
        mock_client_instance = MagicMock()
        mock_client_instance.plan_discharge.return_value = mock_plan
        mock_ai_client.return_value = mock_client_instance
        
        service = DischargePlannerService()
        response = service.process_request(SAMPLE_REQUEST_MINIMAL)
        
        assert response.request_id == "req-discharge-001"
        assert response.discharge_plan.readiness_status == "needs_review"
        assert len(response.discharge_plan.blockers) == 1
        assert response.processing_metadata is not None
        assert "model" in response.processing_metadata
        assert "timestamp" in response.processing_metadata
        assert response.processing_metadata["blocker_count"] == 1
    
    @patch('app.services.discharge_planner_service.AIClient')
    def test_process_request_auto_generates_id(self, mock_ai_client):
        """Test that request_id is auto-generated if not provided."""
        mock_plan = {
            "readiness_status": "ready",
            "readiness_reason": "All criteria met.",
            "blockers": [],
            "medication_reconciliation_concerns": [],
            "follow_up_considerations": [],
            "draft_discharge_summary": "Summary.",
            "disclaimer": "This output supports discharge planning.",
        }
        mock_client_instance = MagicMock()
        mock_client_instance.plan_discharge.return_value = mock_plan
        mock_ai_client.return_value = mock_client_instance
        
        request = DischargePlanningRequest(
            patient_context=SAMPLE_REQUEST_MINIMAL.patient_context,
            clinical_data=SAMPLE_REQUEST_MINIMAL.clinical_data,
            operational_data=SAMPLE_REQUEST_MINIMAL.operational_data,
        )
        service = DischargePlannerService()
        response = service.process_request(request)
        
        assert response.request_id is not None
        assert response.request_id.startswith("req_")
    
    @patch('app.services.discharge_planner_service.AIClient')
    def test_process_request_api_error(self, mock_ai_client):
        """Test handling of API errors."""
        mock_client_instance = MagicMock()
        mock_client_instance.plan_discharge.side_effect = ValueError("OpenAI API error")
        mock_ai_client.return_value = mock_client_instance
        
        service = DischargePlannerService()
        
        with pytest.raises(ValueError, match="OpenAI API error"):
            service.process_request(SAMPLE_REQUEST_MINIMAL)
    
    @patch('app.services.discharge_planner_service.AIClient')
    def test_metadata_includes_blocker_count(self, mock_ai_client):
        """Test that metadata includes blocker count."""
        mock_plan = {
            "readiness_status": "needs_review",
            "readiness_reason": "Blockers.",
            "blockers": [
                {"category": "a", "title": "B1", "reason": "R1"},
                {"category": "b", "title": "B2", "reason": "R2"},
            ],
            "medication_reconciliation_concerns": [],
            "follow_up_considerations": [],
            "draft_discharge_summary": "Summary.",
            "disclaimer": "This output supports discharge planning.",
        }
        mock_client_instance = MagicMock()
        mock_client_instance.plan_discharge.return_value = mock_plan
        mock_ai_client.return_value = mock_client_instance
        
        service = DischargePlannerService()
        response = service.process_request(SAMPLE_REQUEST_MINIMAL)
        
        assert response.processing_metadata["blocker_count"] == 2
        assert response.processing_metadata["provider"] == "openai"
