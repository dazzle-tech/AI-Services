"""Pydantic models for patient timeline request and response schemas."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _strip_required(value: str, field_name: str) -> str:
    """Normalize and validate required string values."""
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be empty")
    return value.strip()


EVENT_TYPE_ALIASES = {
    "diagnoses": "diagnosis",
    "diagnosis": "diagnosis",
    "medication": "medication",
    "medications": "medication",
    "admission": "admission",
    "admissions": "admission",
    "encounter": "admission",
    "encounters": "admission",
    "hospitalization": "admission",
    "hospitalisation": "admission",
    "procedure": "procedure",
    "procedures": "procedure",
    "lab": "lab",
    "labs": "lab",
    "lab_result": "lab",
    "lab_results": "lab",
    "allergy": "allergy",
    "allergies": "allergy",
    "symptom": "symptom",
    "symptoms": "symptom",
    "vital": "vital",
    "vitals": "vital",
    "vital_sign": "vital",
    "vital_signs": "vital",
    "note": "symptom",
    "notes": "symptom",
    "clinical_note": "symptom",
    "admission_note": "admission",
}


class Demographics(BaseModel):
    """Patient demographic details."""

    age: Optional[str] = Field(None, description="Patient age as provided")
    gender: Optional[str] = Field(None, description="Patient gender")

    @field_validator("age", "gender")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim optional strings."""
        if value is None:
            return None
        return value.strip()


class DiagnosisEntry(BaseModel):
    """Diagnosis record."""

    name: str = Field(..., description="Diagnosis name")
    date: str = Field(..., description="Diagnosis date")

    @field_validator("name", "date")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required diagnosis fields."""
        return _strip_required(value, info.field_name)


class MedicationEntry(BaseModel):
    """Medication record."""

    name: str = Field(..., description="Medication name")
    start_date: str = Field(..., description="Medication start date")
    end_date: Optional[str] = Field(None, description="Medication end date")
    status: Optional[str] = Field(None, description="Medication status")

    @field_validator("name", "start_date")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required medication fields."""
        return _strip_required(value, info.field_name)

    @field_validator("end_date", "status")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim optional strings."""
        if value is None:
            return None
        return value.strip()


class LabResultEntry(BaseModel):
    """Laboratory result record."""

    name: str = Field(..., description="Lab name")
    value: str = Field(..., description="Lab value")
    unit: Optional[str] = Field(None, description="Lab unit")
    date: str = Field(..., description="Lab result date")
    flag: Optional[str] = Field(None, description="Lab result flag")

    @field_validator("name", "value", "date")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required lab fields."""
        return _strip_required(value, info.field_name)

    @field_validator("unit", "flag")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim optional strings."""
        if value is None:
            return None
        return value.strip()


class VitalEntry(BaseModel):
    """Vital sign record."""

    name: str = Field(..., description="Vital name")
    value: str = Field(..., description="Vital value")
    date: str = Field(..., description="Vital date")

    @field_validator("name", "value", "date")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required vital fields."""
        return _strip_required(value, info.field_name)


class ProcedureEntry(BaseModel):
    """Procedure record."""

    name: str = Field(..., description="Procedure name")
    date: str = Field(..., description="Procedure date")
    status: Optional[str] = Field(None, description="Procedure status")

    @field_validator("name", "date")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required procedure fields."""
        return _strip_required(value, info.field_name)

    @field_validator("status")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim optional strings."""
        if value is None:
            return None
        return value.strip()


class EncounterEntry(BaseModel):
    """Encounter record."""

    type: str = Field(..., description="Encounter type")
    date: str = Field(..., description="Encounter date")
    reason: Optional[str] = Field(None, description="Encounter reason")

    @field_validator("type", "date")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required encounter fields."""
        return _strip_required(value, info.field_name)

    @field_validator("reason")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim optional strings."""
        if value is None:
            return None
        return value.strip()


class NoteEntry(BaseModel):
    """Clinical note record."""

    date: str = Field(..., description="Note date")
    author: Optional[str] = Field(None, description="Note author")
    type: Optional[str] = Field(None, description="Note type")
    text: str = Field(..., description="Note content")

    @field_validator("date", "text")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required note fields."""
        return _strip_required(value, info.field_name)

    @field_validator("author", "type")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim optional strings."""
        if value is None:
            return None
        return value.strip()


class AllergyEntry(BaseModel):
    """Allergy record."""

    name: str = Field(..., description="Allergy name")
    date: str = Field(..., description="Allergy date")

    @field_validator("name", "date")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required allergy fields."""
        return _strip_required(value, info.field_name)


class PatientDataInput(BaseModel):
    """Input schema for patient timeline generation."""

    patient_id: str = Field(..., description="Unique patient identifier")
    demographics: Optional[Demographics] = Field(None, description="Patient demographics")
    diagnoses: List[DiagnosisEntry] = Field(default_factory=list, description="Diagnoses")
    medications: List[MedicationEntry] = Field(default_factory=list, description="Medications")
    lab_results: List[LabResultEntry] = Field(default_factory=list, description="Lab results")
    vitals: List[VitalEntry] = Field(default_factory=list, description="Vitals")
    procedures: List[ProcedureEntry] = Field(default_factory=list, description="Procedures")
    encounters: List[EncounterEntry] = Field(default_factory=list, description="Encounters")
    notes: List[NoteEntry] = Field(default_factory=list, description="Clinical notes")
    allergies: List[AllergyEntry] = Field(default_factory=list, description="Allergies")

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, value: str) -> str:
        """Validate patient identifier."""
        return _strip_required(value, "patient_id")


class TimelineEvent(BaseModel):
    """Single patient timeline event."""

    date: str = Field(..., description="Event date")
    event_type: Literal[
        "diagnosis",
        "medication",
        "admission",
        "procedure",
        "lab",
        "allergy",
        "symptom",
        "vital"
    ] = Field(..., description="Timeline event category")
    title: str = Field(..., description="Short event title")
    description: str = Field(..., description="Event description")
    clinical_importance: Literal["high", "medium", "low"] = Field(
        ...,
        description="Relative clinical importance"
    )
    source: str = Field(..., description="Originating input field")

    @field_validator("date", "title", "description", "source")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required timeline fields."""
        return _strip_required(value, info.field_name)

    @field_validator("event_type", mode="before")
    @classmethod
    def normalize_event_type(cls, value: str) -> str:
        """Normalize common model aliases to supported event types."""
        normalized = _strip_required(str(value), "event_type").lower().replace("-", "_").replace(" ", "_")
        return EVENT_TYPE_ALIASES.get(normalized, normalized)


class ProcessingMetadata(BaseModel):
    """Timeline generation processing metadata."""

    model: str = Field(..., description="Model used for generation")
    timestamp: str = Field(..., description="Processing timestamp")
    input_fields_count: int = Field(..., description="Number of populated top-level input fields")
    timeline_event_count: int = Field(..., description="Number of timeline events returned")


class TimelineRequest(BaseModel):
    """Request schema for patient timeline generation."""

    request_id: Optional[str] = Field(None, description="Optional unique identifier for this request")
    patient_data: PatientDataInput = Field(..., description="Patient data to convert to a timeline")


class TimelineResponse(BaseModel):
    """Response schema for patient timeline generation."""

    request_id: Optional[str] = Field(None, description="Request identifier")
    timeline: List[TimelineEvent] = Field(default_factory=list, description="Chronological timeline events")
    summary: str = Field(..., description="Request processing summary")
    processing_metadata: ProcessingMetadata = Field(..., description="Additional processing metadata")
