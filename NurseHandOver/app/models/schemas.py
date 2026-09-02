"""Request/response schemas for the handoff service.

The service is STATELESS: the caller (the agent, which owns hospital.db) sends the
patient chart in the request and gets SBAR summaries back. Nothing is persisted here.

Chart fields are deliberately tolerant (Optional) because they are assembled from a
live EMR where any single value may be missing.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Any, List, Optional, Union
from datetime import datetime, timezone
from enum import Enum


class Priority(str, Enum):
    critical = "critical"
    watch = "watch"
    stable = "stable"


# ---------------------------------------------------------------------------
# Patient chart data (supplied by the caller)
# ---------------------------------------------------------------------------

class Vitals(BaseModel):
    """Compact last-reading snapshot (legacy shape). Prefer vital_signs for history."""
    hr: Optional[int] = Field(None, description="Heart rate in bpm")
    bp: Optional[str] = Field(None, description="Blood pressure as 'systolic/diastolic'")
    temp: Optional[float] = Field(None, description="Body temperature in Celsius")
    rr: Optional[int] = Field(None, description="Respiratory rate per minute")
    spo2: Optional[int] = Field(None, description="Oxygen saturation percentage")
    last_updated: Optional[str] = Field(None, description="Time of last reading")


class VitalSignReading(BaseModel):
    """A single vital-sign observation. History may be sent; the service keeps the latest per type."""
    type: str = Field(..., description="Vital type, e.g. hr, bp, temp, rr, spo2")
    value: Union[str, int, float]
    unit: Optional[str] = None
    recorded_at: Optional[str] = Field(None, description="When this reading was taken")


class Medication(BaseModel):
    name: str
    route: Optional[str] = None
    due: Optional[str] = None
    status: Optional[str] = None


class NurseNote(BaseModel):
    time: Optional[str] = Field(None, description="Timestamp of the note")
    text: str


class Allergy(BaseModel):
    """Allergy entry. Resolved items are dropped when the handover chart is assembled."""
    name: str
    reaction: Optional[str] = None
    status: Optional[str] = Field(
        None,
        description="e.g. 'not resolved', 'active', 'resolved'",
    )
    resolved: Optional[bool] = Field(
        None,
        description="If true, the allergy is excluded from the handover",
    )


class ClinicalWarning(BaseModel):
    """Clinical warning/alert. Resolved items are dropped when the handover chart is assembled."""
    text: str
    status: Optional[str] = Field(
        None,
        description="e.g. 'not resolved', 'active', 'resolved'",
    )
    resolved: Optional[bool] = Field(
        None,
        description="If true, the warning is excluded from the handover",
    )


class PendingProcedure(BaseModel):
    """Operation or procedure. Only scheduled/pending (not completed) items are shown."""
    name: str
    status: Optional[str] = Field(
        None,
        description="e.g. pending, scheduled, planned, completed",
    )
    scheduled_at: Optional[str] = None
    notes: Optional[str] = None


class Patient(BaseModel):
    patient_id: str
    name: str
    age: Optional[int] = None
    bed: Optional[str] = None
    diagnosis: Optional[str] = None
    past_medical_history: Optional[str] = None
    hospital_course: Optional[str] = Field(
        None,
        description="Free-text summary of the hospital course this admission",
    )
    admission_date: Optional[str] = None
    vitals: Vitals = Field(default_factory=Vitals)
    vital_signs: List[VitalSignReading] = Field(
        default_factory=list,
        description="Vital history; only the latest reading per type is used",
    )
    medications: List[Medication] = []
    pending_orders: List[str] = []
    pending_procedures: List[PendingProcedure] = Field(
        default_factory=list,
        description="Operations/procedures; completed items are filtered out",
    )
    allergies: List[Allergy] = Field(default_factory=list)
    warnings: List[ClinicalWarning] = Field(default_factory=list)
    alerts: List[str] = []
    nurse_notes: List[NurseNote] = []

    @field_validator("allergies", mode="before")
    @classmethod
    def _coerce_allergies(cls, value: Any) -> Any:
        return _coerce_named_entries(value, name_key="name")

    @field_validator("warnings", mode="before")
    @classmethod
    def _coerce_warnings(cls, value: Any) -> Any:
        return _coerce_named_entries(value, name_key="text")

    @field_validator("pending_procedures", mode="before")
    @classmethod
    def _coerce_procedures(cls, value: Any) -> Any:
        return _coerce_named_entries(value, name_key="name")


def _coerce_named_entries(value: Any, name_key: str) -> Any:
    """Accept bare strings as well as objects for list fields."""
    if value is None:
        return []
    if not isinstance(value, list):
        return value
    coerced = []
    for item in value:
        if isinstance(item, str):
            coerced.append({name_key: item})
        else:
            coerced.append(item)
    return coerced


# ---------------------------------------------------------------------------
# Current-status snapshot (assembled from the chart, not LLM output)
# ---------------------------------------------------------------------------

class PatientCurrentStatus(BaseModel):
    """Filtered view of the patient's current status used for the handoff."""
    patient_id: str
    diagnosis: Optional[str] = None
    past_medical_history: Optional[str] = None
    hospital_course: Optional[str] = None
    allergies: List[Allergy] = Field(default_factory=list)
    warnings: List[ClinicalWarning] = Field(default_factory=list)
    vital_signs: List[VitalSignReading] = Field(default_factory=list)
    pending_procedures: List[PendingProcedure] = Field(default_factory=list)
    generated_at: datetime


# ---------------------------------------------------------------------------
# Generation request / response
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GenerateSummaryRequest(BaseModel):
    """Submitted at shift end to trigger SBAR generation for one or more patients."""
    shift_id: str
    nurse_id: str
    patients: List[Patient] = Field(..., min_length=1)


class SBARSummary(BaseModel):
    """One structured handoff summary for a single patient."""
    patient_id: str
    priority: Priority
    situation: str
    background: str
    assessment: str
    recommendation: str
    flags: List[str] = []
    generated_at: datetime = Field(default_factory=_utcnow)


class PatientSummaryResult(BaseModel):
    """Wraps the result for one patient so failures are isolated — an LLM error on
    one patient never aborts the whole batch."""
    patient_id: str
    success: bool
    summary: Optional[SBARSummary] = None
    current_status: Optional[PatientCurrentStatus] = None
    error: Optional[str] = None


class GenerateSummaryResponse(BaseModel):
    shift_id: str
    status: str = "draft"
    generated_at: datetime = Field(default_factory=_utcnow)
    results: List[PatientSummaryResult]
