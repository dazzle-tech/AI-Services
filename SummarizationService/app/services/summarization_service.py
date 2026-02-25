"""Service layer for clinical summary generation."""
import logging
from typing import Dict, Any
from datetime import datetime

from app.models.schemas import SummaryRequest, SummaryResponse
from app.ai.client import AIClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class SummarizationService:
    """Service for handling clinical summary generation requests."""
    
    def __init__(self):
        """Initialize service with AI client."""
        self.ai_client = AIClient()
    
    def process_request(self, request: SummaryRequest) -> SummaryResponse:
        """
        Process a summary generation request.
        
        Args:
            request: Summary request with patient data
            
        Returns:
            Summary response with generated clinical summary
        """
        try:
            request_id = request.request_id or f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"Processing summary request {request_id}")
            
            # Convert patient data to dict
            patient_data_dict = request.patient_data.dict()
            
            # Log input data (for debugging)
            logger.info(f"Patient data input: {patient_data_dict}")
            
            # Step 1: Generate summary using AI client
            logger.info("Generating clinical summary with OpenAI...")
            summary = self.ai_client.generate_summary(patient_data_dict)
            
            logger.info(f"Summary generated successfully for request {request_id}")
            
            # Step 2: Build response with enhanced metadata
            response = SummaryResponse(
                request_id=request_id,
                ClinicalSummary=summary,
                processing_metadata={
                    "model": settings.openai_model,
                    "timestamp": datetime.now().isoformat(),
                    "input_fields_count": len([k for k, v in patient_data_dict.items() if v]),
                    "summary_length": len(summary),
                    "provider": "openai",
                    "api_version": "v1"
                }
            )
            
            return response
            
        except ValueError as e:
            logger.error(f"Validation error for request {request.request_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing request {request.request_id}: {e}")
            raise ValueError(f"Summary generation failed: {str(e)}")

