"""Formatter for lab_result documents."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.models.schemas import LabMarker, LabResultData, LabResultEntry
from app.services.formatters.base import BaseDocumentFormatter

_MARKERS = {
    "NORMAL_MARKER",
    "UPPER_LIMIT",
    "LOWER_LIMIT",
    "CRITICAL_UPPER",
    "CRITICAL_LOWER",
    "ABNORMAL_MARKER",
    "UNKNOWN",
}
_MARKER_SYNONYMS = {
    "normal": "NORMAL_MARKER",
    "n": "NORMAL_MARKER",
    "normal_marker": "NORMAL_MARKER",
    "within_range": "NORMAL_MARKER",
    "within_limits": "NORMAL_MARKER",
    "high": "UPPER_LIMIT",
    "h": "UPPER_LIMIT",
    "upper": "UPPER_LIMIT",
    "upper_limit": "UPPER_LIMIT",
    "low": "LOWER_LIMIT",
    "l": "LOWER_LIMIT",
    "lower": "LOWER_LIMIT",
    "lower_limit": "LOWER_LIMIT",
    "critical_high": "CRITICAL_UPPER",
    "critical_upper": "CRITICAL_UPPER",
    "hh": "CRITICAL_UPPER",
    "critical_low": "CRITICAL_LOWER",
    "critical_lower": "CRITICAL_LOWER",
    "ll": "CRITICAL_LOWER",
    "critical": "ABNORMAL_MARKER",
    "abnormal": "ABNORMAL_MARKER",
    "abnormal_marker": "ABNORMAL_MARKER",
    "a": "ABNORMAL_MARKER",
    "unknown": "UNKNOWN",
}
_RANGE_SPLIT = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*([+-]?\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)
_RANGE_BOUND = re.compile(r"^\s*(>=|<=|>|<)\s*(.+?)\s*$")


class LabResultFormatter(BaseDocumentFormatter):
    def format(self, extracted_fields: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
        shared_date = self._first(extracted_fields, "resultDate", "result_date", "test_date")
        shared_physician = self._first(
            extracted_fields, "physicianName", "physician_name", "ordering_provider"
        )
        results_raw = extracted_fields.get("results")
        results: List[LabResultEntry] = []
        if isinstance(results_raw, list):
            for item in results_raw:
                if not isinstance(item, dict):
                    continue
                name = self._first(item, "testName", "test_name", "name")
                if not name:
                    continue
                results.append(
                    LabResultEntry(
                        test_name=name,
                        result_date=self._first(item, "resultDate", "result_date", "test_date")
                        or shared_date,
                        result_value=self._first(item, "resultValue", "result_value", "value"),
                        unit=self._first(item, "unit"),
                        normal_range_value=self._normalize_range(
                            self._first(
                                item, "normalRangeValue", "normal_range_value", "reference_range"
                            )
                        ),
                        marker=self._normalize_marker(self._first(item, "marker", "flag")),
                        physician_name=self._first(
                            item, "physicianName", "physician_name", "ordering_provider"
                        )
                        or shared_physician,
                    )
                )

        data = LabResultData(results=results)
        return data.model_dump(by_alias=True)

    def _normalize_marker(self, marker: Optional[str]) -> LabMarker:
        if not marker:
            return "UNKNOWN"
        token = marker.strip().upper().replace(" ", "_").replace("-", "_")
        if token in _MARKERS:
            return token  # type: ignore[return-value]
        mapped = _MARKER_SYNONYMS.get(marker.strip().lower().replace(" ", "_").replace("-", "_"))
        return mapped or "UNKNOWN"  # type: ignore[return-value]

    @classmethod
    def _normalize_range(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        text = value.strip()
        bound = _RANGE_BOUND.match(text)
        if bound:
            return f"{bound.group(1)} {bound.group(2).strip()}"
        split = _RANGE_SPLIT.match(text)
        if split:
            return f"{split.group(1)} - {split.group(2)}"
        return text
