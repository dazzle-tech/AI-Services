"""Formatter for clinical_note / physician_note documents."""
from __future__ import annotations

from typing import Any, Dict

from app.models.schemas import ClinicalNoteData
from app.services.formatters.base import BaseDocumentFormatter


class ClinicalNoteFormatter(BaseDocumentFormatter):
    def format(self, extracted_fields: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
        data = ClinicalNoteData(
            note_date=self._text(extracted_fields.get("note_date")),
            author=self._text(extracted_fields.get("author")),
            note_type=self._text(extracted_fields.get("note_type")),
            subjective=self._text(extracted_fields.get("subjective")),
            objective=self._text(extracted_fields.get("objective")),
            assessment=self._text(extracted_fields.get("assessment")),
            plan=self._text(extracted_fields.get("plan")),
        )
        return data.model_dump()
