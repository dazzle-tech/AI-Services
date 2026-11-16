"""Step 1: file & patient-data validation."""
from __future__ import annotations

import logging
import re
import unicodedata
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

_NAME_NOISE = {
    "mr", "mrs", "ms", "miss", "dr", "prof", "jr", "sr", "ii", "iii", "iv", "md", "phd",
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
    """Cross-checks stable patient-identifying signals extracted from the document
    against the given patient record. Combines the LLM's judgment with deterministic
    guardrails so a clear sex or date-of-birth contradiction can never be waved through.

    Facility-assigned identifiers (patient ID, MRN, chart number) are not compared:
    the same person can carry a different ID when the document was produced somewhere
    other than the facility where they are currently admitted.
    """

    def __init__(self, ai_client: AIClient) -> None:
        self.ai_client = ai_client

    def validate(self, patient: PatientInfo, extracted_text: str) -> ValidationOutcome:
        # Keep the facility ID out of the comparison payload so the model cannot
        # treat a different MRN as a contradiction.
        record = patient.model_dump(exclude_none=True, exclude={"patient_id"})
        raw = self.ai_client.validate_patient_match(record, extracted_text)
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

        # Deterministic guardrails: a clear, structured sex or DOB contradiction
        # always forces INVALID, regardless of the model's is_valid flag.
        # The model often reports the same contradiction in its own words, so keep one
        # row per field and prefer the guardrail values. Patient ID / MRN differences
        # are dropped: they are facility-specific and are not identity.
        deterministic = self._deterministic_checks(patient, signals)
        covered_fields = {item.field for item in deterministic}

        details: List[MismatchDetail] = []
        seen_fields = set(covered_fields)
        dropped_identifier_mismatch = False
        dropped_name_mismatch = False
        for item in self._raw_mismatch_items(raw.get("mismatches")):
            detail = self._coerce_mismatch(item, patient, signals)
            if detail is None or detail.field in seen_fields:
                continue
            if detail.field == "patient_id":
                dropped_identifier_mismatch = True
                continue
            if detail.field == "full_name" and self._names_equivalent(
                patient.full_name, detail.document_value, signals.get("full_name")
            ):
                # Same first and last name; a middle name / initial difference is fine.
                dropped_name_mismatch = True
                continue
            seen_fields.add(detail.field)
            details.append(detail)
        details.extend(deterministic)

        # An "invalid" verdict that rested only on a facility identifier is not a
        # patient mismatch. Any remaining stable-field contradiction still fails.
        reason_text = self._text(raw.get("reason"))
        name_equivalent = self._names_equivalent(patient.full_name, signals.get("full_name"))
        name_only = not details and (
            dropped_name_mismatch
            or (name_equivalent and self._mismatch_field(reason_text or "") == "full_name")
        )
        identifier_only = (
            not details
            and (dropped_identifier_mismatch or self._reason_is_identifier_only(reason_text))
        )
        is_valid = (
            bool(raw.get("is_valid", True)) or identifier_only or name_only
        ) and not deterministic
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

        return mismatches

    @staticmethod
    def _name_tokens(name: Optional[str]) -> List[str]:
        """Normalize a name into ordered tokens, whatever format it was written in.

        Ignores case, accents, punctuation, hyphens, titles and suffixes. 'Last, First
        Middle' is reordered to 'First Middle Last'. Works for non-Latin scripts too.
        """
        if not name or not name.strip():
            return []
        text = unicodedata.normalize("NFKD", name)
        text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
        if "," in text:
            last_part, _, rest = text.partition(",")
            text = f"{rest} {last_part}"
        tokens = re.findall(r"[^\W_]+", text)
        return [t for t in tokens if t not in _NAME_NOISE]

    @staticmethod
    def _token_match(a: str, b: str) -> bool:
        """Equal tokens, or an initial matching a full name ('j' ~ 'jane')."""
        if a == b:
            return True
        if len(a) == 1:
            return b.startswith(a)
        if len(b) == 1:
            return a.startswith(b)
        return False

    @classmethod
    def _distinct_matches(cls, first: str, last: str, tokens: List[str]) -> bool:
        """First and last must match two different tokens (not one token used twice)."""
        first_idx = [i for i, t in enumerate(tokens) if cls._token_match(first, t)]
        last_idx = [i for i, t in enumerate(tokens) if cls._token_match(last, t)]
        return any(i != j for i in first_idx for j in last_idx)

    @classmethod
    def _names_equivalent(cls, record_name: Optional[str], *doc_names: Optional[str]) -> bool:
        """True when two names share the same first + last name, in any format.

        The shorter name's first and last tokens must both appear in the other name, so
        full vs full, full vs first+last, and first+last vs first+last all work
        regardless of middle names, initials, 'Last, First' ordering, hyphens or titles.
        """
        record = cls._name_tokens(record_name)
        if len(record) < 2:
            return False
        for doc_name in doc_names:
            doc = cls._name_tokens(doc_name)
            if len(doc) < 2:
                continue
            short, long_ = (record, doc) if len(record) <= len(doc) else (doc, record)
            if cls._distinct_matches(short[0], short[-1], long_):
                return True
        return False

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
    def _reason_is_identifier_only(reason: Optional[str]) -> bool:
        """True when a free-text reason cites a facility ID and no stable identity field."""
        if not reason:
            return False
        if ValidationService._mismatch_field(reason) != "patient_id":
            return False
        lowered = reason.lower()
        return not any(
            token in lowered
            for token in ("name", "sex", "gender", "date of birth", "birth date", "dob")
        )

    @staticmethod
    def _mismatch_field(text: str) -> Optional[str]:
        lowered = text.lower().replace("_", " ").replace("-", " ")
        if any(
            marker in lowered
            for marker in (
                "patient id",
                "patientid",
                "mrn",
                "medical record number",
                "chart number",
                "account number",
            )
        ):
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
