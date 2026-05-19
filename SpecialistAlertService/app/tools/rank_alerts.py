"""Ranking helpers for final alert ordering."""
from typing import List

from app.models.schemas import Alert


def rank_alerts(alerts: List[Alert]) -> List[Alert]:
    """Rank alerts by severity, urgency category, confidence, and evidence support."""
    category_rank = {
        "urgent_escalation": 6,
        "critical_clinical_alert": 5,
        "medication_safety": 4,
        "specialist_consult": 3,
        "lab_pattern_alert": 2,
        "imaging_follow_up": 2,
        "missing_follow_up": 1,
        "care_gap": 1,
        "duplicate_or_conflict": 1,
    }
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    confidence_rank = {"high": 3, "medium": 2, "low": 1}

    ranked = sorted(
        alerts,
        key=lambda alert: (
            severity_rank.get(alert.severity, 0),
            category_rank.get(alert.category, 0),
            confidence_rank.get(alert.confidence, 0),
            len(alert.supporting_evidence),
        ),
        reverse=True,
    )

    return [
        alert.model_copy(update={"alert_id": f"ALT-{index:03d}"})
        for index, alert in enumerate(ranked, start=1)
    ]
