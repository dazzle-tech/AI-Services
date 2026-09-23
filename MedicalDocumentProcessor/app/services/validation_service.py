"""Step 1: file & patient-data validation."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from app.ai.client import AIClient
from app.models.schemas import PatientInfo, ValidationOutcome

logger = logging.getLogger(__name__)

VALID_SEX_VALUES = {"male", "female", "unspecified"}


class ValidationService:
    """Cross-checks patient-identifying signals extracted from the document against
    the given patient record. Combines the LLM's judgment with deterministic
    guardrails so a clear sex/DOB contradiction can never be waved through."""

    def __init__(self, ai_client: AIClient) -> None:
        self.ai_client = ai_client

    def validate(self, patient: PatientInfo, extracted_text: str) -> ValidationOutcome:
        raw = self.ai_client.validate_patient_match(
            patient.model_dump(exclude_none=True), extracted_text
        )
        return self._normalize(raw, patient)

    def _normalize(self, raw: Dict[str, Any], patient: PatientInfo) -> ValidationOutcome:
        signals_raw = raw.get("extracted_patient_signals")
        signals: Dict[str, Optional[str]] = {
            "full_name": None,
            "sex": None,
            "date_of_birth": None,
            "patient_id": None,
        }
        if isinstance(signals_raw, dict):
            for key in signals:
                value = signals_raw.get(key)
                if isinstance(value, str) and value.strip():
                    signals[key] = value.strip()

        mismatches: List[str] = []
        raw_mismatches = raw.get("mismatches")
        if isinstance(raw_mismatches, list):
            mismatches = [str(m).strip() for m in raw_mismatches if str(m).strip()]

        # Deterministic guardrails: a clear, structured sex or DOB contradiction always
        # forces INVALID, regardless of what the model's own `is_valid` flag says.
        deterministic_mismatches = self._deterministic_checks(patient, signals)
        for item in deterministic_mismatches:
            if item not in mismatches:
                mismatches.append(item)

        is_valid = bool(raw.get("is_valid", True)) and not deterministic_mismatches
        if mismatches and not is_valid:
            reason = "; ".join(mismatches)
        elif not is_valid:
            reason = self._text(raw.get("reason")) or "Document does not match the given patient record."
        else:
            reason = None

        return ValidationOutcome(
            is_valid=is_valid,
            reason=reason,
            mismatches=mismatches,
            extracted_patient_signals=signals,
        )

    def _deterministic_checks(
        self, patient: PatientInfo, signals: Dict[str, Optional[str]]
    ) -> List[str]:
        mismatches: List[str] = []

        doc_sex = (signals.get("sex") or "").strip().lower()
        if patient.sex and doc_sex and doc_sex in VALID_SEX_VALUES and doc_sex != "unspecified":
            if doc_sex != patient.sex:
                mismatches.append(
                    f"Document indicates sex '{doc_sex}' but patient record states '{patient.sex}'"
                )

        doc_dob = signals.get("date_of_birth")
        if patient.date_of_birth and doc_dob:
            try:
                if date.fromisoformat(doc_dob.strip()) != date.fromisoformat(patient.date_of_birth):
                    mismatches.append(
                        f"Document date of birth '{doc_dob}' does not match patient record "
                        f"'{patient.date_of_birth}'"
                    )
            except ValueError:
                pass  # Unparseable doc DOB -- leave to the LLM's own judgment.

        doc_patient_id = signals.get("patient_id")
        if patient.patient_id and doc_patient_id and doc_patient_id.strip() != patient.patient_id.strip():
            mismatches.append(
                f"Document patient ID '{doc_patient_id}' does not match patient record "
                f"'{patient.patient_id}'"
            )

        return mismatches

    @staticmethod
    def _text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
