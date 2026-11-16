"""Pydantic models for role-aware timeline requests and responses."""
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _strip_required(value: str, field_name: str) -> str:
    """Normalize and validate required string values."""
    if value is None or not str(value).strip():
        raise ValueError(f"{field_name} cannot be empty")
    return str(value).strip()


def _strip_optional(value: Optional[str]) -> Optional[str]:
    """Trim optional strings and treat blanks as missing."""
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


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

IMPORTANCE_ALIASES = {
    "high": "high",
    "h": "high",
    "critical": "high",
    "medium": "medium",
    "moderate": "medium",
    "med": "medium",
    "low": "low",
}

SALIENCE_ALIASES = {
    "lead": "lead",
    "primary": "lead",
    "context": "context",
    "supporting": "context",
    "background": "context",
}

SOURCE_ALIASES = {
    "diagnosis": "diagnoses",
    "diagnoses": "diagnoses",
    "medication": "medications",
    "medications": "medications",
    "admission": "encounters",
    "admissions": "encounters",
    "encounter": "encounters",
    "encounters": "encounters",
    "procedure": "procedures",
    "procedures": "procedures",
    "lab": "lab_results",
    "labs": "lab_results",
    "lab_result": "lab_results",
    "lab_results": "lab_results",
    "allergy": "allergies",
    "allergies": "allergies",
    "symptom": "notes",
    "symptoms": "notes",
    "note": "notes",
    "notes": "notes",
    "vital": "vitals",
    "vitals": "vitals",
    "vital_sign": "vitals",
    "vital_signs": "vitals",
}

ViewerRole = Literal["nurse", "radiologist", "cardiologist"]
EventType = Literal[
    "diagnosis",
    "medication",
    "admission",
    "procedure",
    "lab",
    "allergy",
    "symptom",
    "vital",
]
Importance = Literal["high", "medium", "low"]
Salience = Literal["lead", "context"]


class DiagnosisEntry(BaseModel):
    """Diagnosis record."""

    model_config = ConfigDict(extra="ignore")

    name: str
    date: str

    @field_validator("name", "date")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required diagnosis fields."""
        return _strip_required(value, info.field_name)


class MedicationEntry(BaseModel):
    """Medication record. Dose, route, and frequency are not accepted."""

    model_config = ConfigDict(extra="ignore")

    name: str
    start_date: str
    end_date: Optional[str] = None
    status: Optional[str] = None

    @field_validator("name", "start_date")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required medication fields."""
        return _strip_required(value, info.field_name)

    @field_validator("end_date", "status")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim optional medication fields."""
        return _strip_optional(value)


class LabResultEntry(BaseModel):
    """Laboratory result. A single value stays a single value."""

    model_config = ConfigDict(extra="ignore")

    name: str
    value: str
    unit: Optional[str] = None
    date: str
    flag: Optional[str] = None

    @field_validator("name", "value", "date", mode="before")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required lab fields."""
        return _strip_required(value, info.field_name)

    @field_validator("unit", "flag")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim optional lab fields."""
        return _strip_optional(value)


class VitalEntry(BaseModel):
    """Vital sign. Values are stored without a unit."""

    model_config = ConfigDict(extra="ignore")

    name: str
    value: str
    date: str

    @field_validator("name", "value", "date", mode="before")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required vital fields."""
        return _strip_required(value, info.field_name)


class ProcedureEntry(BaseModel):
    """Procedure record."""

    model_config = ConfigDict(extra="ignore")

    name: str
    date: str
    status: Optional[str] = None

    @field_validator("name", "date")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required procedure fields."""
        return _strip_required(value, info.field_name)

    @field_validator("status")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim optional procedure status."""
        return _strip_optional(value)


class EncounterEntry(BaseModel):
    """Encounter record."""

    model_config = ConfigDict(extra="ignore")

    type: str
    date: str
    reason: Optional[str] = None

    @field_validator("type", "date")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required encounter fields."""
        return _strip_required(value, info.field_name)

    @field_validator("reason")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim optional encounter reason."""
        return _strip_optional(value)


class NoteEntry(BaseModel):
    """Clinical note."""

    model_config = ConfigDict(extra="ignore")

    date: str
    text: str
    author: Optional[str] = None
    type: Optional[str] = None

    @field_validator("date", "text")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required note fields."""
        return _strip_required(value, info.field_name)

    @field_validator("author", "type")
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        """Trim optional note fields."""
        return _strip_optional(value)


class AllergyEntry(BaseModel):
    """Allergy record."""

    model_config = ConfigDict(extra="ignore")

    name: str
    date: str

    @field_validator("name", "date")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required allergy fields."""
        return _strip_required(value, info.field_name)


class PatientDataInput(BaseModel):
    """Chart extract accepted by the role-aware timeline endpoint."""

    model_config = ConfigDict(extra="ignore")

    patient_id: str
    age: Optional[str] = None
    gender: Optional[str] = None
    diagnoses: List[DiagnosisEntry] = Field(default_factory=list)
    medications: List[MedicationEntry] = Field(default_factory=list)
    lab_results: List[LabResultEntry] = Field(default_factory=list)
    vitals: List[VitalEntry] = Field(default_factory=list)
    procedures: List[ProcedureEntry] = Field(default_factory=list)
    encounters: List[EncounterEntry] = Field(default_factory=list)
    notes: List[NoteEntry] = Field(default_factory=list)
    allergies: List[AllergyEntry] = Field(default_factory=list)

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, value: str) -> str:
        """Validate the patient identifier."""
        return _strip_required(value, "patient_id")

    @field_validator("age", "gender", mode="before")
    @classmethod
    def normalize_demographics(cls, value: Optional[str]) -> Optional[str]:
        """Keep age and sex as provided, without inferring either one."""
        if value is None:
            return None
        return _strip_optional(str(value))


class TimelineEventDraft(BaseModel):
    """Timeline event returned by the model before this service assigns an id."""

    model_config = ConfigDict(extra="ignore")

    date: str
    event_type: EventType
    title: str
    description: str
    clinical_importance: Importance
    source: str

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

    @field_validator("clinical_importance", mode="before")
    @classmethod
    def normalize_importance(cls, value: str) -> str:
        """Normalize importance aliases."""
        normalized = _strip_required(str(value), "clinical_importance").lower()
        return IMPORTANCE_ALIASES.get(normalized, normalized)

    @field_validator("source")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        """Map source labels onto input field names."""
        parts = []
        for raw in value.split(","):
            token = raw.strip().lower().replace("-", "_").replace(" ", "_")
            if token:
                parts.append(SOURCE_ALIASES.get(token, token))
        if not parts:
            raise ValueError("source cannot be empty")
        return ", ".join(sorted(set(parts)))


class TimelineEvent(TimelineEventDraft):
    """Timeline event returned to the caller."""

    event_id: str

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, value: str) -> str:
        """Validate the event identifier."""
        return _strip_required(value, "event_id")


class RoleHighlight(BaseModel):
    """One ranked explanation that cites a timeline event."""

    model_config = ConfigDict(extra="ignore")

    event_id: str
    why_it_matters: str
    salience: Salience

    @field_validator("event_id", "why_it_matters")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required highlight fields."""
        return _strip_required(value, info.field_name)

    @field_validator("salience", mode="before")
    @classmethod
    def normalize_salience(cls, value: str) -> str:
        """Normalize salience aliases."""
        normalized = _strip_required(str(value), "salience").lower()
        return SALIENCE_ALIASES.get(normalized, normalized)


class HighlightPayload(BaseModel):
    """Model payload for the highlight step."""

    model_config = ConfigDict(extra="ignore")

    role_highlights: List[RoleHighlight] = Field(default_factory=list)
    not_documented: List[str] = Field(default_factory=list)

    @field_validator("not_documented")
    @classmethod
    def strip_gaps(cls, value: List[str]) -> List[str]:
        """Drop blank gap statements."""
        cleaned = []
        for item in value:
            text = _strip_optional(str(item))
            if text:
                cleaned.append(text)
        return cleaned


class ProcessingMetadata(BaseModel):
    """Processing metadata for one role-aware timeline response."""

    model: str
    timestamp: str
    event_count: int
    viewer_role: ViewerRole

    @field_validator("model", "timestamp")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        """Validate required metadata fields."""
        return _strip_required(value, info.field_name)


class RoleTimelineRequest(BaseModel):
    """Request for one shared timeline and the highlights for one role."""

    model_config = ConfigDict(extra="ignore")

    patient_data: PatientDataInput
    viewer_role: ViewerRole
    request_id: Optional[str] = None

    @field_validator("viewer_role", mode="before")
    @classmethod
    def normalize_role(cls, value: str) -> str:
        """Accept role names regardless of case."""
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("request_id")
    @classmethod
    def normalize_request_id(cls, value: Optional[str]) -> Optional[str]:
        """Trim an optional request id."""
        return _strip_optional(value)


class RoleTimelineResponse(BaseModel):
    """Shared timeline, shared summary, and highlights for the requested role."""

    request_id: Optional[str] = None
    timeline: List[TimelineEvent]
    clinical_summary: str
    role_highlights: List[RoleHighlight]
    not_documented: List[str]
    processing_metadata: ProcessingMetadata

    @field_validator("clinical_summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        """Require a clinical summary."""
        return _strip_required(value, "clinical_summary")
