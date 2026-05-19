"""Pydantic models for request and response schemas."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _clean_string(value: Optional[str]) -> Optional[str]:
    """Normalize string values by trimming whitespace."""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


class Demographics(BaseModel):
    """Patient demographics."""

    age: Optional[int] = Field(None, description="Patient age in years")
    sex: Optional[str] = Field(None, description="Patient sex")

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, value: Optional[str]) -> Optional[str]:
        """Trim sex value if provided."""
        return _clean_string(value)


class DiagnosisItem(BaseModel):
    """Diagnosis entry."""

    name: str = Field(..., description="Diagnosis name")
    date: Optional[str] = Field(None, description="Diagnosis date")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Validate diagnosis name."""
        cleaned = _clean_string(value)
        if not cleaned:
            raise ValueError("Diagnosis name cannot be empty")
        return cleaned


class MedicationItem(BaseModel):
    """Medication entry."""

    name: str = Field(..., description="Medication name")
    start_date: Optional[str] = Field(None, description="Medication start date")
    end_date: Optional[str] = Field(None, description="Medication end date")
    status: Optional[str] = Field(None, description="Medication status")

    @field_validator("name", "status", mode="before")
    @classmethod
    def normalize_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim string fields."""
        return _clean_string(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Validate medication name."""
        if not value:
            raise ValueError("Medication name cannot be empty")
        return value


class AllergyItem(BaseModel):
    """Allergy entry."""

    name: str = Field(..., description="Allergy name")
    date: Optional[str] = Field(None, description="Allergy date")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Validate allergy name."""
        cleaned = _clean_string(value)
        if not cleaned:
            raise ValueError("Allergy name cannot be empty")
        return cleaned


class LabResultItem(BaseModel):
    """Lab result entry."""

    name: str = Field(..., description="Lab test name")
    value: str = Field(..., description="Result value")
    unit: Optional[str] = Field(None, description="Result unit")
    reference_range: Optional[str] = Field(None, description="Reference range")
    flag: Optional[str] = Field(None, description="Flag such as high or low")
    date: Optional[str] = Field(None, description="Result date")

    @field_validator("name", "value", "unit", "reference_range", "flag", mode="before")
    @classmethod
    def normalize_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim string fields."""
        return _clean_string(value)

    @field_validator("name", "value")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required lab fields."""
        if not value:
            raise ValueError(f"{info.field_name} cannot be empty")
        return value


class VitalItem(BaseModel):
    """Vital sign entry."""

    name: str = Field(..., description="Vital name")
    value: str = Field(..., description="Vital value")
    unit: Optional[str] = Field(None, description="Vital unit")
    date: Optional[str] = Field(None, description="Vital date")

    @field_validator("name", "value", "unit", mode="before")
    @classmethod
    def normalize_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim string fields."""
        return _clean_string(value)

    @field_validator("name", "value")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required vital fields."""
        if not value:
            raise ValueError(f"{info.field_name} cannot be empty")
        return value


class ImagingReportItem(BaseModel):
    """Imaging report entry."""

    type: str = Field(..., description="Imaging modality or exam type")
    date: Optional[str] = Field(None, description="Report date")
    text: str = Field(..., description="Imaging report text")

    @field_validator("type", "text", mode="before")
    @classmethod
    def normalize_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim string fields."""
        return _clean_string(value)

    @field_validator("type", "text")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required imaging fields."""
        if not value:
            raise ValueError(f"{info.field_name} cannot be empty")
        return value


class ProcedureItem(BaseModel):
    """Procedure entry."""

    name: str = Field(..., description="Procedure name")
    date: Optional[str] = Field(None, description="Procedure date")
    status: Optional[str] = Field(None, description="Procedure status")

    @field_validator("name", "status", mode="before")
    @classmethod
    def normalize_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim string fields."""
        return _clean_string(value)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Validate procedure name."""
        if not value:
            raise ValueError("Procedure name cannot be empty")
        return value


class EncounterItem(BaseModel):
    """Encounter entry."""

    type: str = Field(..., description="Encounter type")
    date: Optional[str] = Field(None, description="Encounter date")
    reason: Optional[str] = Field(None, description="Encounter reason")

    @field_validator("type", "reason", mode="before")
    @classmethod
    def normalize_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim string fields."""
        return _clean_string(value)

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        """Validate encounter type."""
        if not value:
            raise ValueError("Encounter type cannot be empty")
        return value


class NoteItem(BaseModel):
    """Clinical note entry."""

    date: Optional[str] = Field(None, description="Note date")
    author: Optional[str] = Field(None, description="Note author")
    type: Optional[str] = Field(None, description="Note type")
    text: str = Field(..., description="Note text")

    @field_validator("author", "type", "text", mode="before")
    @classmethod
    def normalize_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim string fields."""
        return _clean_string(value)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Validate note text."""
        if not value:
            raise ValueError("Note text cannot be empty")
        return value


class ExistingConsultItem(BaseModel):
    """Existing specialist consultation entry."""

    specialty: str = Field(..., description="Consulted specialty")
    date: Optional[str] = Field(None, description="Consult date")
    status: Optional[str] = Field(None, description="Consult status")

    @field_validator("specialty", "status", mode="before")
    @classmethod
    def normalize_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim string fields."""
        return _clean_string(value)

    @field_validator("specialty")
    @classmethod
    def validate_specialty(cls, value: str) -> str:
        """Validate specialty."""
        if not value:
            raise ValueError("Specialty cannot be empty")
        return value


class DischargeFollowUpItem(BaseModel):
    """Discharge follow-up entry."""

    specialty: str = Field(..., description="Specialty for follow-up")
    scheduled: bool = Field(..., description="Whether follow-up is scheduled")

    @field_validator("specialty")
    @classmethod
    def validate_specialty(cls, value: str) -> str:
        """Validate specialty."""
        cleaned = _clean_string(value)
        if not cleaned:
            raise ValueError("Specialty cannot be empty")
        return cleaned


class PatientRecordInput(BaseModel):
    """Input schema for patient record."""

    patient_id: str = Field(..., description="Patient identifier")
    demographics: Demographics = Field(default_factory=Demographics)
    diagnoses: List[DiagnosisItem] = Field(default_factory=list)
    medications: List[MedicationItem] = Field(default_factory=list)
    allergies: List[AllergyItem] = Field(default_factory=list)
    lab_results: List[LabResultItem] = Field(default_factory=list)
    historical_lab_results: List[LabResultItem] = Field(default_factory=list)
    vitals: List[VitalItem] = Field(default_factory=list)
    imaging_reports: List[ImagingReportItem] = Field(default_factory=list)
    procedures: List[ProcedureItem] = Field(default_factory=list)
    encounters: List[EncounterItem] = Field(default_factory=list)
    notes: List[NoteItem] = Field(default_factory=list)
    existing_consults: List[ExistingConsultItem] = Field(default_factory=list)
    problem_list: List[str] = Field(default_factory=list)
    discharge_follow_up: List[DischargeFollowUpItem] = Field(default_factory=list)

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, value: str) -> str:
        """Validate patient identifier."""
        cleaned = _clean_string(value)
        if not cleaned:
            raise ValueError("patient_id cannot be empty")
        return cleaned

    @field_validator("problem_list", mode="before")
    @classmethod
    def normalize_problem_list(cls, value: Any) -> List[str]:
        """Normalize problem list to non-empty strings."""
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("problem_list must be a list")
        return [item for item in (_clean_string(v) for v in value) if item]


class Alert(BaseModel):
    """Structured clinical alert."""

    alert_id: str = Field(..., description="Unique alert identifier")
    category: Literal[
        "specialist_consult",
        "critical_clinical_alert",
        "medication_safety",
        "lab_pattern_alert",
        "imaging_follow_up",
        "care_gap",
        "duplicate_or_conflict",
        "urgent_escalation",
        "missing_follow_up",
    ] = Field(..., description="Alert category")
    severity: Literal["critical", "high", "medium", "low"] = Field(..., description="Alert severity")
    title: str = Field(..., description="Alert title")
    reason: str = Field(..., description="Clinical reason for the alert")
    recommended_specialty: Optional[str] = Field(
        None,
        description="Recommended specialty to consider, if applicable",
    )
    supporting_evidence: List[str] = Field(
        default_factory=list,
        description="Evidence snippets grounded in the patient record",
    )
    suggested_action: str = Field(..., description="Suggested next action")
    confidence: Literal["high", "medium", "low"] = Field(..., description="Alert confidence")

    @field_validator("alert_id", "title", "reason", "suggested_action", mode="before")
    @classmethod
    def normalize_required_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim required string fields."""
        return _clean_string(value)

    @field_validator("recommended_specialty", mode="before")
    @classmethod
    def normalize_optional_specialty(cls, value: Optional[str]) -> Optional[str]:
        """Trim specialty if present."""
        return _clean_string(value)

    @field_validator("category", "severity", "confidence", mode="before")
    @classmethod
    def normalize_choice_fields(cls, value: Optional[str]) -> Optional[str]:
        """Normalize choice fields to lower snake case."""
        cleaned = _clean_string(value)
        if cleaned is None:
            return None
        return cleaned.lower().replace(" ", "_").replace("-", "_")

    @field_validator("supporting_evidence", mode="before")
    @classmethod
    def normalize_supporting_evidence(cls, value: Any) -> List[str]:
        """Normalize evidence to a list of non-empty strings."""
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("supporting_evidence must be a list or string")
        return [item for item in (_clean_string(v) for v in value) if item]

    @field_validator("alert_id", "title", "reason", "suggested_action")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required string fields."""
        if not value:
            raise ValueError(f"{info.field_name} cannot be empty")
        return value


class AlertRequest(BaseModel):
    """Request schema for alert generation."""

    request_id: Optional[str] = Field(None, description="Optional unique identifier for this request")
    patient_record: PatientRecordInput = Field(..., description="Patient record to analyze")


class AlertResponse(BaseModel):
    """Response schema for alert generation."""

    request_id: Optional[str] = Field(None, description="Request identifier")
    alerts: List[Alert] = Field(default_factory=list, description="Structured clinical alerts")
    summary: str = Field(..., description="Request processing summary")
    processing_metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional processing metadata",
    )
