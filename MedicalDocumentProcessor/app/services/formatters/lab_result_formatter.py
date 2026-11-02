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
_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?")


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
                result_value = self._first(item, "resultValue", "result_value", "value")
                normal_range = self._normalize_range(
                    self._first(item, "normalRangeValue", "normal_range_value", "reference_range")
                )
                results.append(
                    LabResultEntry(
                        test_name=name,
                        result_date=self._first(item, "resultDate", "result_date", "test_date")
                        or shared_date,
                        result_value=result_value,
                        unit=self._first(item, "unit"),
                        normal_range_value=normal_range,
                        marker=self._normalize_marker(
                            self._first(item, "marker", "flag"), result_value, normal_range
                        ),
                        physician_name=self._first(
                            item, "physicianName", "physician_name", "ordering_provider"
                        )
                        or shared_physician,
                    )
                )

        data = LabResultData(results=results)
        return data.model_dump(by_alias=True)

    def _normalize_marker(
        self, marker: Optional[str], result_value: Optional[str], normal_range: Optional[str]
    ) -> LabMarker:
        if not marker:
            return "UNKNOWN"
        token = marker.strip().upper().replace(" ", "_").replace("-", "_")
        if token in _MARKERS:
            return token  # type: ignore[return-value]
        key = marker.strip().lower().replace(" ", "_").replace("-", "_")
        if key == "critical":
            return self._critical_direction(result_value, normal_range)
        mapped = _MARKER_SYNONYMS.get(key)
        return mapped or "UNKNOWN"  # type: ignore[return-value]

    @classmethod
    def _critical_direction(cls, result_value: Optional[str], normal_range: Optional[str]) -> LabMarker:
        """A plain critical flag is upper or lower when the value sits outside the range."""
        number = cls._parse_number(result_value)
        bounds = cls._range_bounds(normal_range)
        if number is None or bounds is None:
            return "ABNORMAL_MARKER"
        low, high, low_inclusive, high_inclusive = bounds
        above = high is not None and (number > high if high_inclusive else number >= high)
        below = low is not None and (number < low if low_inclusive else number <= low)
        if above and not below:
            return "CRITICAL_UPPER"
        if below and not above:
            return "CRITICAL_LOWER"
        return "ABNORMAL_MARKER"

    @staticmethod
    def _parse_number(value: Optional[str]) -> Optional[float]:
        if not value:
            return None
        match = _NUMBER.search(value.replace(",", ""))
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None

    @classmethod
    def _range_bounds(
        cls, value: Optional[str]
    ) -> Optional[tuple[Optional[float], Optional[float], bool, bool]]:
        if not value:
            return None
        split = _RANGE_SPLIT.match(value)
        if split:
            return float(split.group(1)), float(split.group(2)), True, True
        bound = _RANGE_BOUND.match(value)
        if not bound:
            return None
        operator, raw_number = bound.group(1), bound.group(2)
        number = cls._parse_number(raw_number)
        if number is None:
            return None
        if operator == ">=":
            return number, None, True, True
        if operator == ">":
            return number, None, False, True
        if operator == "<=":
            return None, number, True, True
        return None, number, True, False

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
