"""Controlled orchestration for specialist alert generation."""
import logging
from typing import Optional

from app.agent.state import OrchestrationState
from app.ai.client import AIClient
from app.tools.deduplicate_alerts import deduplicate_alerts
from app.tools.extract_risk_signals import extract_risk_signals
from app.tools.rank_alerts import rank_alerts
from app.tools.validate_alerts import validate_alerts

logger = logging.getLogger(__name__)


class AlertOrchestrator:
    """Deterministic orchestrator for internal alert generation workflow."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        """Initialize orchestrator with bounded dependencies."""
        self.ai_client = ai_client or AIClient()

    def run(self, request_id: str, patient_record: dict) -> OrchestrationState:
        """
        Run the internal alert workflow.

        Workflow:
        1. Inspect patient record
        2. Extract deterministic risk signals
        3. Generate candidate alerts
        4. Validate grounding
        5. Deduplicate
        6. Rank and normalize final alerts
        """
        logger.info("Starting controlled alert orchestration for request %s", request_id)

        state = OrchestrationState(
            request_id=request_id,
            patient_record=patient_record,
        )

        state.extracted_signals = extract_risk_signals(patient_record)
        logger.info("Extracted %s deterministic risk signals", len(state.extracted_signals))

        state.candidate_alerts = self.ai_client.generate_alerts(
            patient_record,
            risk_signals=[signal.model_dump() for signal in state.extracted_signals],
        )
        logger.info("Generated %s candidate alerts", len(state.candidate_alerts))

        state.validated_alerts = validate_alerts(
            alerts=state.candidate_alerts,
            patient_record=patient_record,
            risk_signals=state.extracted_signals,
        )
        logger.info("Validated %s grounded alerts", len(state.validated_alerts))

        deduplicated_alerts = deduplicate_alerts(state.validated_alerts)
        logger.info("Deduplicated alerts to %s entries", len(deduplicated_alerts))

        state.final_alerts = rank_alerts(deduplicated_alerts)
        state.dropped_alert_count = max(0, len(state.candidate_alerts) - len(state.final_alerts))

        logger.info(
            "Completed controlled alert orchestration for request %s with %s final alerts",
            request_id,
            len(state.final_alerts),
        )
        return state
