"""Request/response schemas for the handoff service.

The service is STATELESS: the caller (the agent, which owns hospital.db) sends the
patient chart in the request and gets SBAR summaries back. Nothing is persisted here.

Chart fields are deliberately tolerant (Optional) because they are assembled from a
live EMR where any single value may be missing.
"""
from pydantic import BaseModel, Field
from typing import List, Optional
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
    hr: Optional[int] = Field(None, description="Heart rate in bpm")
    bp: Optional[str] = Field(None, description="Blood pressure as 'systolic/diastolic'")
    temp: Optional[float] = Field(None, description="Body temperature in Celsius")
    rr: Optional[int] = Field(None, description="Respiratory rate per minute")
    spo2: Optional[int] = Field(None, description="Oxygen saturation percentage")
    last_updated: Optional[str] = Field(None, description="Time of last reading")


class Medication(BaseModel):
    name: str
    route: Optional[str] = None
    due: Optional[str] = None
    status: Optional[str] = None


class NurseNote(BaseModel):
    time: Optional[str] = Field(None, description="Timestamp of the note")
    text: str


class Patient(BaseModel):
    patient_id: str
    name: str
    age: Optional[int] = None
    bed: Optional[str] = None
    diagnosis: Optional[str] = None
    admission_date: Optional[str] = None
    vitals: Vitals = Field(default_factory=Vitals)
    medications: List[Medication] = []
    pending_orders: List[str] = []
    alerts: List[str] = []
    nurse_notes: List[NurseNote] = []


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
    error: Optional[str] = None


class GenerateSummaryResponse(BaseModel):
    shift_id: str
    status: str = "draft"
    generated_at: datetime = Field(default_factory=_utcnow)
    results: List[PatientSummaryResult]
