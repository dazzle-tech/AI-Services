"""Request/response schemas for the handoff service.

The service is STATELESS: the caller (the agent, which owns hospital.db) sends the
patient chart in the request and gets SBAR summaries back. Nothing is persisted here.

Chart fields are deliberately tolerant (Optional) because they are assembled from a
live EMR where any single value may be missing.
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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
    category: Optional[str] = Field(None, description="e.g. Drug, Food")
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
    category: Optional[str] = Field(None, description="e.g. Infection Control")
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
    name: str = Field(default="not recorded")
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
    """Internal generation request. Exactly one patient per call."""
    handover_nurse: str
    patient: Patient
    shift_id: str = "unspecified"

    @model_validator(mode="before")
    @classmethod
    def _normalize_request(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        nurse = _handover_nurse_name(data.get("handover_nurse")) or _handover_nurse_name(
            data.get("nurse_id")
        )
        if not nurse:
            raise ValueError("handover_nurse is required (signed-in nurse)")
        data["handover_nurse"] = nurse
        if data.get("patient") is not None:
            if data.get("patients"):
                raise ValueError("Send a single 'patient' (or patient_data); do not also send 'patients'")
            return data
        patients = data.get("patients")
        if patients is None:
            return data
        if not isinstance(patients, list) or len(patients) != 1:
            raise ValueError("Exactly one patient is allowed per API call")
        data["patient"] = patients[0]
        data.pop("patients", None)
        return data


def _handover_nurse_name(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(
            value.get("name")
            or value.get("display_name")
            or value.get("full_name")
            or value.get("id")
            or ""
        ).strip()
    return str(value).strip()


# ---------------------------------------------------------------------------
# CMS / EMR inbound chart (the public generate body)
# ---------------------------------------------------------------------------

class CmsAllergy(BaseModel):
    model_config = ConfigDict(extra="ignore")
    allergy_description: str
    allergy_type_description: Optional[str] = None
    status: Optional[str] = None
    resolved: Optional[bool] = None
    is_resolved: Optional[bool] = None


class CmsWarning(BaseModel):
    model_config = ConfigDict(extra="ignore")
    virus_description: str
    type: Optional[str] = None
    status: Optional[str] = None
    resolved: Optional[bool] = None
    is_resolved: Optional[bool] = None


class CmsHistoryRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    record_type: Optional[str] = None
    record_description: Optional[str] = None


class CmsDiagnosis(BaseModel):
    model_config = ConfigDict(extra="ignore")
    diagnosis_type: Optional[str] = None
    diagnosis_code: Optional[str] = None
    diagnosis_description: Optional[str] = None


class CmsPendingOperation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    operation_name: str
    requested_date: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class CmsPatientData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    allergies: List[CmsAllergy] = Field(default_factory=list)
    warnings: List[CmsWarning] = Field(default_factory=list)
    last_hospital_course: Optional[str] = None
    past_medical_history: Union[List[CmsHistoryRecord], str, None] = None
    diagnosis: Union[List[CmsDiagnosis], str, None] = None
    vital_signs: Any = None
    pending_operations: List[CmsPendingOperation] = Field(default_factory=list)
    name: Optional[str] = None
    patient_id: Optional[str] = None


class CmsHandoverRequest(BaseModel):
    """Public generate body from the hospital CMS."""
    model_config = ConfigDict(extra="ignore")
    handover_nurse: str
    patient_data: CmsPatientData

    @model_validator(mode="before")
    @classmethod
    def _require_handover_nurse(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        nurse = _handover_nurse_name(data.get("handover_nurse")) or _handover_nurse_name(
            data.get("nurse_id")
        )
        if not nurse:
            raise ValueError("handover_nurse is required (signed-in nurse)")
        data["handover_nurse"] = nurse
        return data


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
    formatted_text: Optional[str] = Field(
        None,
        description="SBAR as markdown with bold section headlines",
    )

    @model_validator(mode="after")
    def _fill_formatted_text(self):
        if not self.formatted_text:
            from app.services.format_markdown import render_sbar_markdown

            self.formatted_text = render_sbar_markdown(self)
        return self


class PatientSummaryResult(BaseModel):
    """Wraps the result for one patient so failures are isolated — an LLM error on
    one patient never aborts the whole batch."""
    patient_id: str
    success: bool
    summary: Optional[SBARSummary] = None
    current_status: Optional[PatientCurrentStatus] = None
    formatted_text: Optional[str] = Field(
        None,
        description="Full handover as markdown with bold section headlines",
    )
    error: Optional[str] = None


class GenerateSummaryResponse(BaseModel):
    """Public generate response — markdown handover plus who it was generated for."""
    formatted_text: str
    generated_by_ai_for: str = Field(..., description="Signed-in handover nurse")
    generated_at: datetime = Field(default_factory=_utcnow)
