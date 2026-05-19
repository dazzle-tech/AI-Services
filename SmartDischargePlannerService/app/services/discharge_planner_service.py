"""Service layer for discharge planning assessment."""
import logging
from typing import Dict, Any
from datetime import datetime

from app.models.schemas import (
    DischargePlanningRequest,
    DischargePlanningResponse,
    DischargePlan,
    DischargeBlocker,
)
from app.ai.client import AIClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class DischargePlannerService:
    """Service for handling discharge planning assessment requests."""
    
    def __init__(self):
        """Initialize service with AI client."""
        self.ai_client = AIClient()
    
    def process_request(self, request: DischargePlanningRequest) -> DischargePlanningResponse:
        """
        Process a discharge planning assessment request.
        
        Args:
            request: Discharge planning request with patient context and data
            
        Returns:
            Discharge planning response with structured assessment
        """
        try:
            request_id = request.request_id or f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info(f"Processing discharge planning request {request_id}")
            
            input_data = {
                "patient_context": request.patient_context.model_dump(),
                "clinical_data": request.clinical_data.model_dump(),
                "operational_data": request.operational_data.model_dump(),
            }
            
            logger.info("Generating discharge planning assessment with OpenAI...")
            plan_dict = self.ai_client.plan_discharge(input_data)
            
            logger.info(f"Discharge plan generated successfully for request {request_id}")
            
            blockers = [
                DischargeBlocker(**b) for b in plan_dict.get("blockers", [])
            ]
            
            discharge_plan = DischargePlan(
                readiness_status=plan_dict.get("readiness_status", "unclear"),
                readiness_reason=plan_dict.get("readiness_reason", ""),
                blockers=blockers,
                medication_reconciliation_concerns=plan_dict.get(
                    "medication_reconciliation_concerns", []
                ),
                follow_up_considerations=plan_dict.get(
                    "follow_up_considerations", []
                ),
                draft_discharge_summary=plan_dict.get("draft_discharge_summary", ""),
                disclaimer=plan_dict.get(
                    "disclaimer",
                    "This output supports discharge planning and does not replace clinician judgment."
                ),
            )
            
            response = DischargePlanningResponse(
                request_id=request_id,
                discharge_plan=discharge_plan,
                summary="Discharge planning assessment generated successfully.",
                processing_metadata={
                    "model": settings.openai_model,
                    "timestamp": datetime.now().isoformat(),
                    "blocker_count": len(blockers),
                    "provider": "openai",
                    "api_version": "v1",
                }
            )
            
            return response
            
        except ValueError as e:
            logger.error(f"Validation error for request {request.request_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing request {request.request_id}: {e}")
            raise ValueError(f"Discharge planning failed: {str(e)}")
