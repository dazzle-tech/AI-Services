"""Integration tests for service layer."""
import pytest
from unittest.mock import patch, MagicMock
from app.services.summarization_service import SummarizationService
from app.models.schemas import SummaryRequest
from tests.fixtures.sample_data import SAMPLE_REQUEST_MINIMAL, SAMPLE_REQUEST_COMPLETE


class TestSummarizationService:
    """Test SummarizationService."""
    
    @patch('app.services.summarization_service.AIClient')
    def test_process_request_success(self, mock_ai_client):
        """Test successful request processing."""
        # Mock AI client
        mock_client_instance = MagicMock()
        mock_client_instance.generate_summary.return_value = "A 45-year-old male with Type 2 Diabetes."
        mock_ai_client.return_value = mock_client_instance
        
        # Create service and process request
        service = SummarizationService()
        response = service.process_request(SAMPLE_REQUEST_MINIMAL)
        
        # Verify response
        assert response.request_id == "test-001"
        assert "Diabetes" in response.ClinicalSummary
        assert response.processing_metadata is not None
        assert "model" in response.processing_metadata
        assert "timestamp" in response.processing_metadata
    
    @patch('app.services.summarization_service.AIClient')
    def test_process_request_auto_generates_id(self, mock_ai_client):
        """Test that request_id is auto-generated if not provided."""
        mock_client_instance = MagicMock()
        mock_client_instance.generate_summary.return_value = "Test summary"
        mock_ai_client.return_value = mock_client_instance
        
        request = SummaryRequest(patient_data=SAMPLE_REQUEST_MINIMAL.patient_data)
        service = SummarizationService()
        response = service.process_request(request)
        
        assert response.request_id is not None
        assert response.request_id.startswith("req_")
    
    @patch('app.services.summarization_service.AIClient')
    def test_process_request_with_complete_data(self, mock_ai_client):
        """Test processing request with complete patient data."""
        mock_client_instance = MagicMock()
        mock_client_instance.generate_summary.return_value = "A 58-year-old male with STEMI."
        mock_ai_client.return_value = mock_client_instance
        
        service = SummarizationService()
        response = service.process_request(SAMPLE_REQUEST_COMPLETE)
        
        assert response.request_id == "test-002"
        assert len(response.ClinicalSummary) > 0
        assert response.processing_metadata["input_fields_count"] > 0
    
    @patch('app.services.summarization_service.AIClient')
    def test_process_request_api_error(self, mock_ai_client):
        """Test handling of API errors."""
        mock_client_instance = MagicMock()
        mock_client_instance.generate_summary.side_effect = ValueError("OpenAI API error")
        mock_ai_client.return_value = mock_client_instance
        
        service = SummarizationService()
        
        with pytest.raises(ValueError, match="Summary generation failed"):
            service.process_request(SAMPLE_REQUEST_MINIMAL)
    
    @patch('app.services.summarization_service.AIClient')
    def test_metadata_includes_summary_length(self, mock_ai_client):
        """Test that metadata includes summary length."""
        summary_text = "A 45-year-old male with Type 2 Diabetes."
        mock_client_instance = MagicMock()
        mock_client_instance.generate_summary.return_value = summary_text
        mock_ai_client.return_value = mock_client_instance
        
        service = SummarizationService()
        response = service.process_request(SAMPLE_REQUEST_MINIMAL)
        
        assert response.processing_metadata["summary_length"] == len(summary_text)
        assert response.processing_metadata["provider"] == "openai"

