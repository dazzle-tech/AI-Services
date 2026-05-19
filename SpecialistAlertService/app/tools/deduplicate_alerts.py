"""Deterministic deduplication helpers for alerts."""
from typing import Dict, List, Tuple

from app.models.schemas import Alert


def deduplicate_alerts(alerts: List[Alert]) -> List[Alert]:
    """Remove overlapping alerts while preserving the strongest entry in each group."""
    grouped_alerts: Dict[Tuple[str, str, str], Alert] = {}

    for alert in alerts:
        dedupe_key = (
            alert.category,
            _normalize(alert.title),
            _normalize(alert.recommended_specialty or ""),
        )
        existing_alert = grouped_alerts.get(dedupe_key)
        if existing_alert is None or _alert_priority(alert) > _alert_priority(existing_alert):
            grouped_alerts[dedupe_key] = alert

    return list(grouped_alerts.values())


def _alert_priority(alert: Alert) -> Tuple[int, int, int]:
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    confidence_rank = {"high": 3, "medium": 2, "low": 1}
    return (
        severity_rank.get(alert.severity, 0),
        confidence_rank.get(alert.confidence, 0),
        len(alert.supporting_evidence),
    )


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())
