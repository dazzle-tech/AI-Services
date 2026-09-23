"""Formatter for lab_result documents."""
from __future__ import annotations

from typing import Any, Dict, List

from app.models.schemas import LabResultData, LabResultEntry
from app.services.formatters.base import BaseDocumentFormatter

VALID_FLAGS = {"normal", "high", "low", "critical"}
_FLAG_SYNONYMS = {
    "normal_marker": "normal",
    "within_range": "normal",
    "within_limits": "normal",
    "abnormal_marker": "high",
    "critical_upper": "critical",
    "critical_lower": "critical",
    "lower_limit": "low",
    "upper_limit": "high",
    "unknown": "normal",
}


class LabResultFormatter(BaseDocumentFormatter):
    def format(self, extracted_fields: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
        results_raw = extracted_fields.get("results")
        results: List[Dict[str, Any]] = []
        if isinstance(results_raw, list):
            for item in results_raw:
                if not isinstance(item, dict):
                    continue
                name = self._text(item.get("test_name") or item.get("name"))
                if not name:
                    continue
                results.append(
                    LabResultEntry(
                        test_name=name,
                        value=self._text(item.get("value")),
                        unit=self._text(item.get("unit")),
                        reference_range=self._text(item.get("reference_range")),
                        flag=self._normalize_flag(item.get("flag")),
                    ).model_dump()
                )

        data = LabResultData(
            test_date=self._text(extracted_fields.get("test_date")),
            ordering_provider=self._text(extracted_fields.get("ordering_provider")),
            results=[LabResultEntry(**r) for r in results],
        )
        return data.model_dump()

    def _normalize_flag(self, flag: Any) -> str:
        text = self._text(flag)
        if not text:
            return "normal"
        lowered = text.lower()
        if lowered in VALID_FLAGS:
            return lowered
        return _FLAG_SYNONYMS.get(lowered, "normal")
