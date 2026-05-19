"""Integration tests for service layer."""
from unittest.mock import MagicMock

import pytest

from app.agent.state import OrchestrationState, RiskSignal
from app.models.schemas import AlertRequest
from app.services.alert_service import SpecialistAlertService
from tests.fixtures.sample_data import SAMPLE_ALERT, SAMPLE_REQUEST_COMPLETE, SAMPLE_REQUEST_MINIMAL


class TestSpecialistAlertService:
    """Test SpecialistAlertService."""

    def test_process_request_success(self):
        """Test successful request processing."""
        orchestrator = MagicMock()
        orchestrator.run.return_value = OrchestrationState(
            request_id="test-001",
            patient_record=SAMPLE_REQUEST_MINIMAL.patient_record.model_dump(),
            extracted_signals=[
                RiskSignal(
                    signal_type="vital_instability",
                    category="urgent_escalation",
                    severity="high",
                    summary="Fever may indicate acute clinical deterioration",
                    evidence=["Vital temperature 39.1 C on 2026-03-16"],
                    recommended_specialty="Infectious Disease",
                )
            ],
            candidate_alerts=[SAMPLE_ALERT],
            validated_alerts=[SAMPLE_ALERT],
            final_alerts=[SAMPLE_ALERT],
            dropped_alert_count=0,
        )

        service = SpecialistAlertService(orchestrator=orchestrator)
        response = service.process_request(SAMPLE_REQUEST_MINIMAL)

        assert response.request_id == "test-001"
        assert response.summary == "Clinical alerts generated successfully."
        assert len(response.alerts) == 1
        assert response.alerts[0].alert_id == "ALT-001"
        assert response.processing_metadata["alert_count"] == 1
        assert response.processing_metadata["risk_signal_count"] == 1
        assert "timestamp" in response.processing_metadata

    def test_process_request_auto_generates_id(self):
        """Test that request_id is auto-generated if not provided."""
        orchestrator = MagicMock()
        request = AlertRequest(patient_record=SAMPLE_REQUEST_MINIMAL.patient_record)

        generated_state = OrchestrationState(
            request_id="generated-id",
            patient_record=request.patient_record.model_dump(),
            extracted_signals=[],
            candidate_alerts=[],
            validated_alerts=[],
            final_alerts=[],
            dropped_alert_count=0,
        )
        orchestrator.run.return_value = generated_state

        service = SpecialistAlertService(orchestrator=orchestrator)
        response = service.process_request(request)

        assert response.request_id is not None
        assert response.request_id.startswith("req_")
        orchestrator.run.assert_called_once()

    def test_process_request_with_complete_data(self):
        """Test processing request with complete patient data."""
        orchestrator = MagicMock()
        orchestrator.run.return_value = OrchestrationState(
            request_id="test-002",
            patient_record=SAMPLE_REQUEST_COMPLETE.patient_record.model_dump(),
            extracted_signals=[
                RiskSignal(
                    signal_type="lab_abnormality",
                    category="lab_pattern_alert",
                    severity="high",
                    summary="Abnormal lab result for Creatinine",
                    evidence=["Lab Creatinine 1.8 mg/dL on 2026-03-16 flag high"],
                    recommended_specialty="Nephrology",
                )
            ],
            candidate_alerts=[SAMPLE_ALERT, SAMPLE_ALERT],
            validated_alerts=[SAMPLE_ALERT],
            final_alerts=[SAMPLE_ALERT],
            dropped_alert_count=1,
        )

        service = SpecialistAlertService(orchestrator=orchestrator)
        response = service.process_request(SAMPLE_REQUEST_COMPLETE)

        assert response.request_id == "test-002"
        assert len(response.alerts) == 1
        assert response.processing_metadata["input_sections_count"] > 0
        assert response.processing_metadata["candidate_alert_count"] == 2
        assert response.processing_metadata["validated_alert_count"] == 1
        assert response.processing_metadata["dropped_alert_count"] == 1

    def test_process_request_returns_empty_summary_when_no_alerts(self):
        """Test service response when no alerts are returned."""
        orchestrator = MagicMock()
        orchestrator.run.return_value = OrchestrationState(
            request_id="test-001",
            patient_record=SAMPLE_REQUEST_MINIMAL.patient_record.model_dump(),
            extracted_signals=[],
            candidate_alerts=[],
            validated_alerts=[],
            final_alerts=[],
            dropped_alert_count=0,
        )

        service = SpecialistAlertService(orchestrator=orchestrator)
        response = service.process_request(SAMPLE_REQUEST_MINIMAL)

        assert response.alerts == []
        assert response.summary == "No clinically meaningful alerts were identified from the provided record."

    def test_process_request_api_error(self):
        """Test handling of orchestration errors."""
        orchestrator = MagicMock()
        orchestrator.run.side_effect = ValueError("Malformed alert JSON after 3 attempts")

        service = SpecialistAlertService(orchestrator=orchestrator)

        with pytest.raises(ValueError, match="Malformed alert JSON"):
            service.process_request(SAMPLE_REQUEST_MINIMAL)
