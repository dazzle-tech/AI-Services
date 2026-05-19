"""Integration tests for the internal alert orchestrator."""
from unittest.mock import MagicMock

from app.agent.orchestrator import AlertOrchestrator
from tests.fixtures.sample_data import SAMPLE_ALERT, SAMPLE_PATIENT_COMPLETE, UNGROUNDED_ALERT


class TestAlertOrchestrator:
    """Test the controlled alert orchestration flow."""

    def test_orchestrator_runs_controlled_workflow(self):
        """Test signal extraction, validation, deduplication, and ranking."""
        ai_client = MagicMock()
        ai_client.generate_alerts.return_value = [SAMPLE_ALERT, SAMPLE_ALERT.model_copy()]

        orchestrator = AlertOrchestrator(ai_client=ai_client)
        state = orchestrator.run(
            request_id="test-001",
            patient_record=SAMPLE_PATIENT_COMPLETE.model_dump(),
        )

        assert len(state.extracted_signals) > 0
        assert len(state.candidate_alerts) == 2
        assert len(state.validated_alerts) >= 1
        assert len(state.final_alerts) == 1
        assert state.final_alerts[0].alert_id == "ALT-001"
        ai_client.generate_alerts.assert_called_once()

    def test_orchestrator_drops_ungrounded_alerts(self):
        """Test that alerts without grounded evidence are removed."""
        ai_client = MagicMock()
        ai_client.generate_alerts.return_value = [UNGROUNDED_ALERT]

        orchestrator = AlertOrchestrator(ai_client=ai_client)
        state = orchestrator.run(
            request_id="test-002",
            patient_record=SAMPLE_PATIENT_COMPLETE.model_dump(),
        )

        assert len(state.candidate_alerts) == 1
        assert state.validated_alerts == []
        assert state.final_alerts == []
        assert state.dropped_alert_count == 1
