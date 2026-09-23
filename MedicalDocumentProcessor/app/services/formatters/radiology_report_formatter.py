"""Formatter for radiology_report / imaging_report documents."""
from __future__ import annotations

from typing import Any, Dict

from app.models.schemas import RadiologyReportData
from app.services.formatters.base import BaseDocumentFormatter


class RadiologyReportFormatter(BaseDocumentFormatter):
    def format(self, extracted_fields: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
        data = RadiologyReportData(
            study_date=self._text(extracted_fields.get("study_date")),
            modality=self._text(extracted_fields.get("modality")),
            body_part_examined=self._text(extracted_fields.get("body_part_examined")),
            ordering_provider=self._text(extracted_fields.get("ordering_provider")),
            findings=self._text(extracted_fields.get("findings")),
            impression=self._text(extracted_fields.get("impression")),
        )
        return data.model_dump()
