"""Pydantic models for request and response schemas."""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Patient metadata
# ---------------------------------------------------------------------------
# No shared "Patient" schema exists elsewhere in this codebase (every service defines
# its own inline patient shape with inconsistent fields). This is a minimal schema with
# at least `sex` and `date_of_birth`, since those are required for Step 1 validation.
Sex = Literal["male", "female", "unspecified"]


class PatientInfo(BaseModel):
    """Minimal patient metadata supplied alongside the uploaded document."""

    patient_id: Optional[str] = Field(None, description="Patient identifier")
    full_name: Optional[str] = Field(None, description="Patient's full name")
    sex: Optional[Sex] = Field(None, description="Patient sex: male, female, or unspecified")
    date_of_birth: Optional[str] = Field(
        None, description="Patient date of birth, ISO format YYYY-MM-DD"
    )

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not str(value).strip():
            return None
        try:
            date.fromisoformat(str(value).strip())
        except ValueError as exc:
            raise ValueError("date_of_birth must be an ISO date (YYYY-MM-DD)") from exc
        return str(value).strip()


class ExistingDocumentSummary(BaseModel):
    """Minimal summary of a document already on file, used by the relevance check
    (Step 2) to determine whether the newly uploaded document is superseded."""

    document_type: str = Field(..., description="Document type of the existing record")
    document_date: Optional[str] = Field(None, description="ISO date of the existing record")


# ---------------------------------------------------------------------------
# Document types (extensible; new types can be added here without touching the
# pipeline logic -- only the formatter registry needs a matching entry)
# ---------------------------------------------------------------------------
class DocumentType(str, Enum):
    LAB_RESULT = "lab_result"
    RADIOLOGY_REPORT = "radiology_report"
    IMAGING_REPORT = "imaging_report"
    DISCHARGE_SUMMARY = "discharge_summary"
    PRESCRIPTION = "prescription"
    PHYSICIAN_NOTE = "physician_note"
    CLINICAL_NOTE = "clinical_note"
    OTHER = "other"

    @classmethod
    def values(cls) -> List[str]:
        return [member.value for member in cls]

    @classmethod
    def coerce(cls, value: Optional[str]) -> "DocumentType":
        if not value:
            return cls.OTHER
        normalized = str(value).strip().lower().replace(" ", "_").replace("-", "_")
        try:
            return cls(normalized)
        except ValueError:
            return cls.OTHER


# ---------------------------------------------------------------------------
# Pipeline step outcomes (internal, also useful for unit testing each step)
# ---------------------------------------------------------------------------
class ValidationOutcome(BaseModel):
    is_valid: bool
    reason: Optional[str] = None
    mismatches: List[str] = Field(default_factory=list)
    extracted_patient_signals: Dict[str, Optional[str]] = Field(default_factory=dict)


class RelevanceOutcome(BaseModel):
    is_relevant: bool
    reason: Optional[str] = None
    apparent_document_type: Optional[str] = None
    document_date: Optional[str] = None
    relevance_window_days: Optional[int] = None


class TranslationOutcome(BaseModel):
    detected_language: str
    translated: bool = False
    translated_text: Optional[str] = None


# ---------------------------------------------------------------------------
# Per-document-type structured shapes (Step 4 output). Extensible: add a new model +
# formatter for new document types without changing core pipeline logic.
# ---------------------------------------------------------------------------
class LabResultEntry(BaseModel):
    test_name: str
    value: Optional[str] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    flag: Literal["normal", "high", "low", "critical"] = "normal"


class LabResultData(BaseModel):
    document_type: Literal["lab_result"] = "lab_result"
    test_date: Optional[str] = None
    ordering_provider: Optional[str] = None
    results: List[LabResultEntry] = Field(default_factory=list)


class RadiologyReportData(BaseModel):
    document_type: Literal["radiology_report", "imaging_report"] = "radiology_report"
    study_date: Optional[str] = None
    modality: Optional[str] = None
    body_part_examined: Optional[str] = None
    ordering_provider: Optional[str] = None
    findings: Optional[str] = None
    impression: Optional[str] = None


class PrescriptionMedicationEntry(BaseModel):
    name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    duration: Optional[str] = None
    instructions: Optional[str] = None


class PrescriptionData(BaseModel):
    document_type: Literal["prescription"] = "prescription"
    prescription_date: Optional[str] = None
    prescribing_provider: Optional[str] = None
    medications: List[PrescriptionMedicationEntry] = Field(default_factory=list)


class ClinicalNoteData(BaseModel):
    document_type: Literal["clinical_note", "physician_note"] = "clinical_note"
    note_date: Optional[str] = None
    author: Optional[str] = None
    note_type: Optional[str] = None
    subjective: Optional[str] = None
    objective: Optional[str] = None
    assessment: Optional[str] = None
    plan: Optional[str] = None


class GenericDocumentData(BaseModel):
    """Fallback structured shape for document types without a dedicated formatter --
    mirrors this repo's own generic.html fallback-for-unknown convention."""

    document_type: str = "other"
    summary: Optional[str] = None
    content: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level response envelope
# ---------------------------------------------------------------------------
# No {data, error, meta} wrapper exists anywhere in this codebase -- every service
# returns its typed response model directly as JSON, so this mirrors that exactly.
PipelineStatus = Literal["invalid", "irrelevant", "processed"]


class ProcessDocumentResponse(BaseModel):
    status: PipelineStatus
    reason: Optional[str] = Field(
        None, description="Populated when status is 'invalid' or 'irrelevant'"
    )
    detected_language: Optional[str] = None
    translated: bool = False
    document_type: Optional[str] = None
    structured_data: Optional[Dict[str, Any]] = Field(
        None, description="Populated only when status is 'processed'"
    )
    raw_extracted_text: str = Field(
        "", description="Always included for traceability/debugging"
    )
    request_id: Optional[str] = None
    processing_metadata: Dict[str, Any] = Field(default_factory=dict)
