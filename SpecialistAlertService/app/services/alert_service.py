"""Service layer for specialist alert generation."""
import json
import logging
from datetime import datetime
from typing import Dict, Optional

from app.agent.orchestrator import AlertOrchestrator
from app.core.config import settings
from app.models.schemas import AlertRequest, AlertResponse

logger = logging.getLogger(__name__)


class SpecialistAlertService:
    """Service for handling specialist alert generation requests."""

    def __init__(self, orchestrator: Optional[AlertOrchestrator] = None):
        """Initialize service and defer heavy dependencies until request time."""
        self.orchestrator = orchestrator

    def process_request(self, request: AlertRequest) -> AlertResponse:
        """
        Process an alert generation request.

        Args:
            request: Alert request with patient record

        Returns:
            Alert response with structured alerts
        """
        try:
            request_id = request.request_id or f"req_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            logger.info("Processing specialist alert request %s", request_id)

            patient_record_dict = request.patient_record.model_dump()
            payload_length = len(json.dumps(patient_record_dict, ensure_ascii=False))
            if payload_length > settings.max_input_length:
                raise ValueError(
                    f"Patient record exceeds maximum input length of {settings.max_input_length} characters"
                )

            logger.info("Patient record input: %s", patient_record_dict)
            logger.info("Running controlled specialist alert orchestration...")

            orchestrator = self.orchestrator or AlertOrchestrator()

            orchestration_state = orchestrator.run(
                request_id=request_id,
                patient_record=patient_record_dict,
            )
            processed_alerts = orchestration_state.final_alerts

            logger.info(
                "Specialist alerts generated successfully for request %s with %s alerts",
                request_id,
                len(processed_alerts),
            )

            summary = (
                "Clinical alerts generated successfully."
                if processed_alerts
                else "No clinically meaningful alerts were identified from the provided record."
            )

            return AlertResponse(
                request_id=request_id,
                alerts=processed_alerts,
                summary=summary,
                processing_metadata={
                    "model": settings.openai_model,
                    "timestamp": datetime.now().isoformat(),
                    "alert_count": len(processed_alerts),
                    "input_sections_count": self._count_populated_sections(patient_record_dict),
                    "risk_signal_count": len(orchestration_state.extracted_signals),
                    "candidate_alert_count": len(orchestration_state.candidate_alerts),
                    "validated_alert_count": len(orchestration_state.validated_alerts),
                    "dropped_alert_count": orchestration_state.dropped_alert_count,
                    "workflow": [
                        "inspect_patient_record",
                        "extract_risk_signals",
                        "generate_candidate_alerts",
                        "validate_grounding",
                        "deduplicate_alerts",
                        "rank_alerts",
                    ],
                    "provider": "openai",
                    "api_version": "v1",
                },
            )

        except ValueError as e:
            logger.error("Validation error for request %s: %s", request.request_id, e)
            raise
        except Exception as e:
            logger.error("Unexpected error processing request %s: %s", request.request_id, e)
            raise ValueError(f"Alert generation failed: {str(e)}")

    def _count_populated_sections(self, patient_record: Dict[str, object]) -> int:
        """Count populated top-level sections in the patient record."""
        return len([key for key, value in patient_record.items() if value not in (None, "", [], {})])
