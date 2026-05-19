"""Unit tests for deterministic alert tools."""
from app.tools.deduplicate_alerts import deduplicate_alerts
from app.tools.extract_risk_signals import extract_risk_signals
from app.tools.rank_alerts import rank_alerts
from app.tools.validate_alerts import validate_alerts
from tests.fixtures.sample_data import SAMPLE_ALERT, SAMPLE_PATIENT_COMPLETE, UNGROUNDED_ALERT


class TestExtractRiskSignals:
    """Test deterministic signal extraction."""

    def test_extract_risk_signals_finds_expected_patterns(self):
        """Test signal extraction from a rich patient record."""
        signals = extract_risk_signals(SAMPLE_PATIENT_COMPLETE.model_dump())

        categories = {signal.category for signal in signals}
        assert "lab_pattern_alert" in categories
        assert "urgent_escalation" in categories
        assert "missing_follow_up" in categories


class TestValidateAlerts:
    """Test alert grounding and normalization."""

    def test_validate_alerts_keeps_grounded_alerts(self):
        """Test validation keeps alerts with supporting evidence."""
        validated = validate_alerts(
            alerts=[SAMPLE_ALERT],
            patient_record=SAMPLE_PATIENT_COMPLETE.model_dump(),
            risk_signals=extract_risk_signals(SAMPLE_PATIENT_COMPLETE.model_dump()),
        )

        assert len(validated) == 1
        assert validated[0].confidence in {"high", "medium", "low"}
        assert len(validated[0].supporting_evidence) >= 1

    def test_validate_alerts_drops_ungrounded_alerts(self):
        """Test validation removes alerts that cannot be grounded."""
        validated = validate_alerts(
            alerts=[UNGROUNDED_ALERT],
            patient_record=SAMPLE_PATIENT_COMPLETE.model_dump(),
            risk_signals=extract_risk_signals(SAMPLE_PATIENT_COMPLETE.model_dump()),
        )

        assert validated == []


class TestDeduplicateAndRankAlerts:
    """Test deduplication and ranking helpers."""

    def test_deduplicate_alerts_keeps_strongest_alert(self):
        """Test duplicate alerts are collapsed."""
        duplicate = SAMPLE_ALERT.model_copy(update={"confidence": "medium"})
        deduplicated = deduplicate_alerts([duplicate, SAMPLE_ALERT])

        assert len(deduplicated) == 1
        assert deduplicated[0].confidence == "high"

    def test_rank_alerts_reindexes_and_orders(self):
        """Test final ranking assigns sequential alert ids."""
        lower_priority = SAMPLE_ALERT.model_copy(
            update={
                "alert_id": "ALT-777",
                "severity": "medium",
                "category": "missing_follow_up",
                "confidence": "medium",
            }
        )

        ranked = rank_alerts([lower_priority, SAMPLE_ALERT])

        assert ranked[0].alert_id == "ALT-001"
        assert ranked[0].severity == "critical"
        assert ranked[1].alert_id == "ALT-002"
