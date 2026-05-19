"""Deterministic statistics intent classifier.

This classifier is intentionally conservative: it only returns True when the query
strongly indicates aggregate/analytics intent and does not appear to target a
specific patient (e.g., includes an MRN).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.mrn import extract_mrn


@dataclass(frozen=True)
class StatisticsIntentClassifier:
    """
    Deterministic "statistics" intent classifier.

    Rules:
    - Must contain an aggregate/analytics signal OR a "how many admissions" pattern.
    - May mention an analytic entity (diagnosis/admissions/departments); if omitted, the parser defaults.
    - Time range is enforced by the parser (classification does not require it).
    - Must NOT include an MRN (avoid routing patient-specific queries).
    """

    # Signals that strongly imply aggregate analytics (not patient-specific).
    _ANALYTICS_SIGNALS = (
        "top",
        "most common",
        "busiest",
        "trend",
        "trends",
        "distribution",
        "count by",
        "counts by",
        "group by",
        "breakdown",
    )

    _ENTITY_SIGNALS = (
        "diagnosis",
        "diagnoses",
        "dx",
        "admission",
        "admissions",
        "admitted",
        "department",
        "departments",
        "unit",
        "units",
        "ward",
        "wards",
    )

    _HOW_MANY_ADMISSIONS_RE = re.compile(
        r"\bhow\s+many\s+admissions\b", re.IGNORECASE
    )

    _PATIENT_SPECIFIC_GUARD_RE = re.compile(
        r"\b(this\s+patient|that\s+patient|the\s+patient|patient\s+named)\b",
        re.IGNORECASE,
    )

    @classmethod
    def is_statistics_query(cls, text: str) -> bool:
        tl = (text or "").strip().lower()
        if not tl:
            return False

        # If the user provided an MRN, always treat as patient-specific (data pipeline).
        if extract_mrn(text, allow_standalone=True):
            return False

        # Guard against obvious patient-specific phrasing even without MRN.
        if cls._PATIENT_SPECIFIC_GUARD_RE.search(tl):
            return False

        has_signal = any(sig in tl for sig in cls._ANALYTICS_SIGNALS) or bool(
            cls._HOW_MANY_ADMISSIONS_RE.search(tl)
        )
        if not has_signal:
            return False

        # Prefer entity signals when available, but allow generic analytics queries like "trend".
        return True
