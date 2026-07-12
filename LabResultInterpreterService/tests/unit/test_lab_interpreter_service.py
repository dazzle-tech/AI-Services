"""Unit tests for lab interpreter severity normalization."""

from app.services.lab_interpreter_service import LabInterpreterService


class TestLabInterpreterSeverityNormalization:
    """Regression tests for deterministic severity derivation."""

    def test_multiple_findings_with_critical_flag_produce_critical(self):
        """Critical flags should override all other severity cues."""
        service = LabInterpreterService()
        normalized = service._normalize_interpretation(
            interpretation_dict={
                "severity": "moderate",
                "key_findings": [
                    {"lab_name": "Potassium", "flag": "critical_upper", "finding": "Potassium is high"},
                    {"lab_name": "Sodium", "flag": "normal_marker", "finding": "Sodium is normal"},
                ],
            },
            lab_results=[
                {"name": "Potassium", "value": "7.2", "flag": "critical_upper"},
                {"name": "Sodium", "value": "140", "flag": "normal_marker"},
            ],
            historical_lab_results=[],
        )

        assert normalized["severity"] == "critical"

    def test_borderline_flags_produce_moderate(self):
        """Borderline and out-of-range flags should map to moderate."""
        service = LabInterpreterService()
        normalized = service._normalize_interpretation(
            interpretation_dict={
                "severity": "high",
                "key_findings": [
                    {"lab_name": "Hemoglobin", "flag": "lower_limit", "finding": "Hemoglobin is slightly below range"},
                ],
            },
            lab_results=[
                {"name": "Hemoglobin", "value": "11.2", "flag": "lower_limit"},
            ],
            historical_lab_results=[],
        )

        assert normalized["severity"] == "moderate"

    def test_all_normal_flags_produce_low(self):
        """Normal markers should resolve to low severity when no higher-risk flags exist."""
        service = LabInterpreterService()
        normalized = service._normalize_interpretation(
            interpretation_dict={
                "severity": "high",
                "key_findings": [
                    {"lab_name": "WBC", "flag": "normal_marker", "finding": "WBC is normal"},
                ],
            },
            lab_results=[
                {"name": "WBC", "value": "7.0", "flag": "normal_marker"},
            ],
            historical_lab_results=[],
        )

        assert normalized["severity"] == "low"

    def test_no_key_findings_falls_back_to_model_severity(self):
        """When there are no normalized findings, the model-provided severity should be preserved."""
        service = LabInterpreterService()
        normalized = service._normalize_interpretation(
            interpretation_dict={
                "severity": "high",
                "key_findings": [],
            },
            lab_results=[],
            historical_lab_results=[],
        )

        assert normalized["severity"] == "high"
