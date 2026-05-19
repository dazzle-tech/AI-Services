from __future__ import annotations

from .models import Finding


def make_finding(
    *,
    finding_code: str,
    finding_text: str,
    location: str | None,
    confidence: float,
    priority: str = "ROUTINE",
) -> Finding:
    return Finding(
        finding_code=finding_code,
        finding_text=finding_text,
        location=location,
        confidence=confidence,
        priority=priority,
        radiologist_review_required=True,
    )
