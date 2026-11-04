"""Step 1: file & patient-data validation."""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.ai.client import AIClient
from app.models.schemas import MismatchDetail, PatientInfo, ValidationOutcome

logger = logging.getLogger(__name__)

VALID_SEX_VALUES = {"male", "female", "unspecified"}

_FIELD_ALIASES = {
    "dob": "date_of_birth",
    "date of birth": "date_of_birth",
    "birth date": "date_of_birth",
    "birthdate": "date_of_birth",
    "patient id": "patient_id",
    "patientid": "patient_id",
    "mrn": "patient_id",
    "medical record number": "patient_id",
    "gender": "sex",
    "name": "full_name",
    "full name": "full_name",
    "patient name": "full_name",
}

_KNOWN_FIELDS = {"full_name", "sex", "date_of_birth", "patient_id"}

_QUOTED = re.compile(r"['\"]([^'\"]+)['\"]")
_DOC_HAS = re.compile(
    r"document\s+(?:has|indicates(?:\s+\w+)?)\s+['\"]?([^'\".,;]+)['\"]?",
    re.IGNORECASE,
)
_RECORD_HAS = re.compile(
    r"(?:patient\s+)?record\s+(?:has|states)\s+['\"]?([^'\".,;]+)['\"]?",
    re.IGNORECASE,
)

_FIELD_LABELS = {
    "sex": "sex",
    "date_of_birth": "date of birth",
    "patient_id": "patient ID",
    "full_name": "name",
}


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

        # Deterministic guardrails: a clear, structured sex, DOB, or patient-id
        # contradiction always forces INVALID, regardless of the model's is_valid flag.
        # The model often reports the same contradiction in its own words, so keep one
        # row per field and prefer the guardrail values.
        deterministic = self._deterministic_checks(patient, signals)
        covered_fields = {item.field for item in deterministic}

        details: List[MismatchDetail] = []
        seen_fields = set(covered_fields)
        for item in self._raw_mismatch_items(raw.get("mismatches")):
            detail = self._coerce_mismatch(item, patient, signals)
            if detail is None or detail.field in seen_fields:
                continue
            seen_fields.add(detail.field)
            details.append(detail)
        details.extend(deterministic)

        is_valid = bool(raw.get("is_valid", True)) and not deterministic
        messages = [self._message(item) for item in details]
        if messages and not is_valid:
            reason = "; ".join(messages)
        elif not is_valid:
            reason = self._text(raw.get("reason")) or "Document does not match the given patient record."
        else:
            reason = None

        return ValidationOutcome(
            is_valid=is_valid,
            reason=reason,
            mismatches=messages,
            mismatch_details=details,
            extracted_patient_signals=signals,
        )

    def _deterministic_checks(
        self, patient: PatientInfo, signals: Dict[str, Optional[str]]
    ) -> List[MismatchDetail]:
        mismatches: List[MismatchDetail] = []

        doc_sex = (signals.get("sex") or "").strip().lower()
        if patient.sex and doc_sex and doc_sex in VALID_SEX_VALUES and doc_sex != "unspecified":
            if doc_sex != patient.sex:
                mismatches.append(
                    MismatchDetail(
                        field="sex",
                        patient_record_value=patient.sex,
                        document_value=doc_sex,
                    )
                )

        doc_dob = signals.get("date_of_birth")
        if patient.date_of_birth and doc_dob:
            try:
                if date.fromisoformat(doc_dob.strip()) != date.fromisoformat(patient.date_of_birth):
                    mismatches.append(
                        MismatchDetail(
                            field="date_of_birth",
                            patient_record_value=patient.date_of_birth,
                            document_value=doc_dob.strip(),
                        )
                    )
            except ValueError:
                pass  # Unparseable doc DOB -- leave to the LLM's own judgment.

        doc_patient_id = signals.get("patient_id")
        if patient.patient_id and doc_patient_id and doc_patient_id.strip() != patient.patient_id.strip():
            mismatches.append(
                MismatchDetail(
                    field="patient_id",
                    patient_record_value=patient.patient_id.strip(),
                    document_value=doc_patient_id.strip(),
                )
            )

        return mismatches

    @staticmethod
    def _raw_mismatch_items(raw_mismatches: Any) -> List[Any]:
        if isinstance(raw_mismatches, dict):
            return [raw_mismatches]
        if isinstance(raw_mismatches, list):
            return raw_mismatches
        return []

    def _coerce_mismatch(
        self, item: Any, patient: PatientInfo, signals: Dict[str, Optional[str]]
    ) -> Optional[MismatchDetail]:
        if isinstance(item, dict):
            field = self._normalize_field(item.get("field"))
            record_value = self._text(item.get("patient_record_value"))
            document_value = self._text(item.get("document_value"))
            if field is None:
                message = self._text(item.get("message") or item.get("reason") or item.get("description"))
                if not message:
                    return None
                field = self._mismatch_field(message) or "other"
                parsed_record, parsed_document = self._values_from_text(message)
                record_value = record_value or parsed_record
                document_value = document_value or parsed_document
        elif isinstance(item, str) and item.strip():
            text = item.strip()
            field = self._mismatch_field(text) or "other"
            record_value, document_value = self._values_from_text(text)
        else:
            return None

        if field in _KNOWN_FIELDS:
            record_value = record_value or self._patient_value(patient, field)
            document_value = document_value or self._text(signals.get(field))

        if not record_value and not document_value and field == "other":
            return None

        return MismatchDetail(
            field=field,
            patient_record_value=record_value,
            document_value=document_value,
        )

    @staticmethod
    def _patient_value(patient: PatientInfo, field: str) -> Optional[str]:
        value = getattr(patient, field, None)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_field(value: Any) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().lower().replace("_", " ").replace("-", " ")
        normalized = " ".join(normalized.split())
        if not normalized:
            return None
        if normalized.replace(" ", "_") in _KNOWN_FIELDS:
            return normalized.replace(" ", "_")
        return _FIELD_ALIASES.get(normalized)

    @staticmethod
    def _mismatch_field(text: str) -> Optional[str]:
        lowered = text.lower().replace("_", " ").replace("-", " ")
        if "patient id" in lowered or "mrn" in lowered:
            return "patient_id"
        if "date of birth" in lowered or "birth date" in lowered or " dob " in f" {lowered} ":
            return "date_of_birth"
        if "sex" in lowered or "gender" in lowered:
            return "sex"
        if "name" in lowered:
            return "full_name"
        return None

    @staticmethod
    def _values_from_text(text: str) -> Tuple[Optional[str], Optional[str]]:
        doc = _DOC_HAS.search(text)
        record = _RECORD_HAS.search(text)
        if doc and record:
            return record.group(1).strip() or None, doc.group(1).strip() or None
        quotes = [item.strip() for item in _QUOTED.findall(text) if item.strip()]
        if len(quotes) >= 2:
            return quotes[1], quotes[0]
        if len(quotes) == 1:
            return None, quotes[0]
        return None, None

    @staticmethod
    def _message(detail: MismatchDetail) -> str:
        label = _FIELD_LABELS.get(detail.field, detail.field.replace("_", " "))
        if detail.field == "sex" and detail.document_value and detail.patient_record_value:
            return (
                f"Document indicates sex '{detail.document_value}' but patient record states "
                f"'{detail.patient_record_value}'"
            )
        if detail.document_value and detail.patient_record_value:
            return (
                f"Document {label} '{detail.document_value}' does not match patient record "
                f"'{detail.patient_record_value}'"
            )
        return f"Document {label} does not match the patient record"

    @staticmethod
    def _text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
