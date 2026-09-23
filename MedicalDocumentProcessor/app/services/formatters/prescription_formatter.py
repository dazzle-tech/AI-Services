"""Formatter for prescription documents."""
from __future__ import annotations

from typing import Any, Dict, List

from app.models.schemas import PrescriptionData, PrescriptionMedicationEntry
from app.services.formatters.base import BaseDocumentFormatter


class PrescriptionFormatter(BaseDocumentFormatter):
    def format(self, extracted_fields: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
        meds_raw = extracted_fields.get("medications")
        medications: List[PrescriptionMedicationEntry] = []
        if isinstance(meds_raw, list):
            for item in meds_raw:
                if not isinstance(item, dict):
                    continue
                name = self._text(item.get("name"))
                if not name:
                    continue
                medications.append(
                    PrescriptionMedicationEntry(
                        name=name,
                        dosage=self._text(item.get("dosage")),
                        frequency=self._text(item.get("frequency")),
                        route=self._text(item.get("route")),
                        duration=self._text(item.get("duration")),
                        instructions=self._text(item.get("instructions")),
                    )
                )

        data = PrescriptionData(
            prescription_date=self._text(extracted_fields.get("prescription_date")),
            prescribing_provider=self._text(extracted_fields.get("prescribing_provider")),
            medications=medications,
        )
        return data.model_dump()
