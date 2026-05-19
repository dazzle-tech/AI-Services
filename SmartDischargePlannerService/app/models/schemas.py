"""Pydantic models for discharge planning request and response schemas."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List, Any


# --- Request Schemas ---

class VitalReading(BaseModel):
    """A single vital sign reading."""
    name: str = Field(..., description="Vital name (e.g., temperature, oxygen_saturation)")
    value: str = Field(..., description="Value of the vital")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    timestamp: Optional[str] = Field(None, description="ISO timestamp of the reading")


class PendingTest(BaseModel):
    """A pending test or procedure."""
    name: str = Field(..., description="Test or procedure name")
    status: str = Field(default="pending", description="Status of the test")


class ClinicalNote(BaseModel):
    """A clinical note entry."""
    type: str = Field(..., description="Note type (e.g., progress_note)")
    timestamp: Optional[str] = Field(None, description="ISO timestamp")
    text: str = Field(..., description="Note content")


class FollowUpAppointment(BaseModel):
    """Follow-up appointment information."""
    service: str = Field(..., description="Service or specialty")
    scheduled: bool = Field(default=False, description="Whether appointment is scheduled")


class PatientEducation(BaseModel):
    """Patient education topic with completion status."""
    topic: str = Field(..., description="Education topic")
    completed: bool = Field(default=False, description="Whether education was completed")


class EquipmentNeed(BaseModel):
    """Equipment need for discharge."""
    name: str = Field(..., description="Equipment name (e.g., home oxygen)")
    confirmed: bool = Field(default=False, description="Whether equipment is confirmed")


class PatientContext(BaseModel):
    """Patient context for discharge planning."""
    patient_id: str = Field(..., description="Patient identifier")
    admission_date: Optional[str] = Field(None, description="Admission date")
    primary_diagnosis: str = Field(..., description="Primary diagnosis")
    secondary_diagnoses: List[str] = Field(default_factory=list, description="Secondary diagnoses")
    current_status: Optional[str] = Field(None, description="Current clinical status")


class ClinicalData(BaseModel):
    """Clinical data for discharge assessment."""
    latest_vitals: List[VitalReading] = Field(default_factory=list, description="Latest vital signs")
    pending_tests: List[PendingTest] = Field(default_factory=list, description="Pending tests")
    active_problems: List[str] = Field(default_factory=list, description="Active problems")
    medications_current: List[str] = Field(default_factory=list, description="Current medications")
    medications_planned_for_discharge: List[str] = Field(
        default_factory=list,
        description="Medications planned for discharge"
    )
    notes: List[ClinicalNote] = Field(default_factory=list, description="Clinical notes")


class OperationalData(BaseModel):
    """Operational data for discharge planning."""
    follow_up_appointments: List[FollowUpAppointment] = Field(
        default_factory=list,
        description="Follow-up appointments"
    )
    patient_education: List[PatientEducation] = Field(
        default_factory=list,
        description="Patient education topics"
    )
    transport_status: Optional[str] = Field(None, description="Transport availability")
    home_support: Optional[str] = Field(None, description="Home support availability")
    equipment_needs: List[EquipmentNeed] = Field(
        default_factory=list,
        description="Equipment needs"
    )


class DischargePlanningRequest(BaseModel):
    """Request schema for discharge planning assessment."""
    request_id: Optional[str] = Field(None, description="Optional unique identifier for this request")
    patient_context: PatientContext = Field(..., description="Patient context")
    clinical_data: ClinicalData = Field(..., description="Clinical data")
    operational_data: OperationalData = Field(..., description="Operational data")

    @field_validator("patient_context", mode="before")
    @classmethod
    def ensure_patient_context(cls, v: Any) -> Any:
        """Ensure patient_context is provided."""
        if v is None:
            raise ValueError("patient_context is required")
        return v

    @field_validator("clinical_data", mode="before")
    @classmethod
    def ensure_clinical_data(cls, v: Any) -> Any:
        """Ensure clinical_data is provided."""
        if v is None:
            raise ValueError("clinical_data is required")
        return v

    @field_validator("operational_data", mode="before")
    @classmethod
    def ensure_operational_data(cls, v: Any) -> Any:
        """Ensure operational_data is provided."""
        if v is None:
            raise ValueError("operational_data is required")
        return v


# --- Response Schemas ---

class DischargeBlocker(BaseModel):
    """A single discharge blocker."""
    category: str = Field(..., description="Blocker category")
    title: str = Field(..., description="Short title for the blocker")
    reason: str = Field(..., description="Explanation of the blocker")


class DischargePlan(BaseModel):
    """Structured discharge planning output."""
    readiness_status: str = Field(
        ...,
        description="Assessment: ready, needs_review, not_ready, or unclear"
    )
    readiness_reason: str = Field(..., description="Explanation for the readiness status")
    blockers: List[DischargeBlocker] = Field(
        default_factory=list,
        description="Identified discharge blockers"
    )
    medication_reconciliation_concerns: List[str] = Field(
        default_factory=list,
        description="Medication reconciliation concerns"
    )
    follow_up_considerations: List[str] = Field(
        default_factory=list,
        description="Follow-up considerations"
    )
    draft_discharge_summary: str = Field(
        ...,
        description="Draft discharge planning summary"
    )
    disclaimer: str = Field(
        ...,
        description="Disclaimer that this supports planning only, not final decision"
    )


class DischargePlanningResponse(BaseModel):
    """Response schema for discharge planning assessment."""
    request_id: Optional[str] = Field(None, description="Request identifier")
    discharge_plan: DischargePlan = Field(..., description="Structured discharge plan")
    summary: str = Field(
        default="Discharge planning assessment generated successfully.",
        description="Human-readable summary message"
    )
    processing_metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Processing metadata (model, timestamp, blocker_count)"
    )
