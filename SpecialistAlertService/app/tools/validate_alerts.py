"""Validation and grounding helpers for candidate alerts."""
import re
from typing import Dict, Iterable, List, Optional

from app.agent.state import RiskSignal
from app.models.schemas import Alert
from app.tools.extract_risk_signals import build_evidence_catalog


def validate_alerts(
    alerts: List[Alert],
    patient_record: Dict[str, object],
    risk_signals: List[RiskSignal],
) -> List[Alert]:
    """Keep only alerts that can be grounded in the record and normalize wording."""
    evidence_catalog = build_evidence_catalog(patient_record)
    evidence_catalog.extend(
        evidence
        for signal in risk_signals
        for evidence in signal.evidence
    )
    normalized_catalog = [_normalize_text(item) for item in evidence_catalog if item]

    validated_alerts: List[Alert] = []
    for alert in alerts:
        grounded_evidence = _ground_evidence(alert, evidence_catalog, normalized_catalog)
        if not grounded_evidence:
            continue

        updated_alert = alert.model_copy(
            update={
                "supporting_evidence": grounded_evidence[:5],
                "confidence": _adjust_confidence(
                    alert.confidence,
                    grounded_evidence,
                    alert.supporting_evidence,
                ),
                "suggested_action": _normalize_suggested_action(
                    alert.suggested_action,
                    alert.recommended_specialty,
                ),
            }
        )
        validated_alerts.append(updated_alert)

    return validated_alerts


def _ground_evidence(
    alert: Alert,
    evidence_catalog: List[str],
    normalized_catalog: List[str],
) -> List[str]:
    grounded: List[str] = []

    for evidence in alert.supporting_evidence:
        normalized_evidence = _normalize_text(evidence)
        if not normalized_evidence:
            continue

        for catalog_item, normalized_item in zip(evidence_catalog, normalized_catalog):
            if normalized_evidence in normalized_item or normalized_item in normalized_evidence:
                grounded.append(catalog_item)
                break

    if grounded:
        return _deduplicate_strings(grounded)

    keywords = _extract_keywords(
        " ".join(
            part
            for part in [
                alert.title,
                alert.reason,
                alert.recommended_specialty or "",
                alert.category,
            ]
            if part
        )
    )
    if not keywords:
        return []

    fallback = []
    for catalog_item, normalized_item in zip(evidence_catalog, normalized_catalog):
        matches = sum(1 for keyword in keywords if keyword in normalized_item)
        if matches >= 2:
            fallback.append(catalog_item)

    return _deduplicate_strings(fallback[:5])


def _adjust_confidence(current_confidence: str, grounded_evidence: List[str], original_evidence: List[str]) -> str:
    if current_confidence == "low":
        return "low"
    if len(grounded_evidence) >= max(1, len(original_evidence)):
        return current_confidence
    if len(grounded_evidence) >= 2:
        return "medium" if current_confidence == "high" else current_confidence
    return "low"


def _normalize_suggested_action(action: str, specialty: Optional[str]) -> str:
    cleaned = action.strip()
    lowered = cleaned.lower()
    cautious_phrases = (
        "consider",
        "may indicate",
        "review for possible",
        "determine whether",
    )
    if any(phrase in lowered for phrase in cautious_phrases):
        return cleaned

    if specialty:
        return (
            f"Review for possible {specialty} involvement and determine whether consultation is needed."
        )
    return "Review for possible clinical significance and determine whether further evaluation is needed."


def _extract_keywords(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [token for token in tokens if len(token) >= 4]


def _normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _deduplicate_strings(values: Iterable[str]) -> List[str]:
    unique_values: List[str] = []
    seen = set()
    for value in values:
        normalized = _normalize_text(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_values.append(value)
    return unique_values
