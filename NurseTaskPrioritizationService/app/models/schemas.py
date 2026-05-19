"""Pydantic models for request and response schemas."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List, Any
from datetime import datetime


class UnitContext(BaseModel):
    """Unit context information."""
    unit_name: str = Field(..., description="Name of the unit (e.g., Medical Ward A)")
    shift: str = Field(..., description="Current shift (e.g., day, night)")
    generated_at: str = Field(..., description="ISO timestamp when data was generated")


class NurseContext(BaseModel):
    """Nurse context information."""
    nurse_id: str = Field(..., description="Nurse identifier")
    assigned_rooms: List[str] = Field(default_factory=list, description="List of assigned room numbers")


class VitalReading(BaseModel):
    """Single vital sign reading."""
    name: str = Field(..., description="Vital name (e.g., oxygen_saturation, heart_rate)")
    value: str = Field(..., description="Value of the vital")
    unit: str = Field(default="", description="Unit of measurement")
    timestamp: str = Field(..., description="ISO timestamp of the reading")


class LabAlert(BaseModel):
    """Lab result with abnormal flag."""
    name: str = Field(..., description="Lab name (e.g., potassium)")
    value: str = Field(..., description="Lab value")
    unit: str = Field(default="", description="Unit of measurement")
    flag: str = Field(default="", description="Flag (e.g., low, high, critical)")
    timestamp: str = Field(..., description="ISO timestamp")


class MedicationTask(BaseModel):
    """Medication administration task."""
    task_id: str = Field(..., description="Task identifier")
    medication_name: str = Field(..., description="Name of medication")
    due_time: str = Field(..., description="ISO timestamp when due")
    status: str = Field(default="pending", description="Task status")
    priority_hint: Optional[str] = Field(None, description="Optional hint (e.g., time_sensitive)")


class NursingTask(BaseModel):
    """General nursing task."""
    task_id: str = Field(..., description="Task identifier")
    title: str = Field(..., description="Task title")
    due_time: str = Field(..., description="ISO timestamp when due")
    status: str = Field(default="pending", description="Task status")


class Note(BaseModel):
    """Clinical note."""
    type: str = Field(..., description="Note type (e.g., nurse_note)")
    timestamp: str = Field(..., description="ISO timestamp")
    text: str = Field(..., description="Note content")


class PatientInput(BaseModel):
    """Patient data for prioritization."""
    patient_id: str = Field(..., description="Patient identifier")
    room: str = Field(..., description="Room number")
    patient_risk_flags: List[str] = Field(default_factory=list, description="Risk flags (e.g., fall_risk)")
    vitals: List[VitalReading] = Field(default_factory=list, description="Recent vital signs")
    lab_alerts: List[LabAlert] = Field(default_factory=list, description="Abnormal lab results")
    medication_tasks: List[MedicationTask] = Field(default_factory=list, description="Pending medication tasks")
    nursing_tasks: List[NursingTask] = Field(default_factory=list, description="Pending nursing tasks")
    notes: List[Note] = Field(default_factory=list, description="Clinical notes")


class TaskPrioritizationRequest(BaseModel):
    """Request schema for task prioritization."""
    request_id: Optional[str] = Field(None, description="Optional unique identifier for this request")
    unit_context: UnitContext = Field(..., description="Unit context")
    nurse_context: NurseContext = Field(..., description="Nurse context")
    patients: List[PatientInput] = Field(..., description="List of patients with tasks and data")


class PrioritizedTask(BaseModel):
    """A single prioritized task in the response."""
    rank: int = Field(..., description="Priority rank (1 = most urgent)")
    patient_id: str = Field(..., description="Patient identifier")
    room: str = Field(..., description="Room number")
    task_id: str = Field(..., description="Task identifier")
    task_type: str = Field(..., description="Task type (e.g., clinical_reassessment, medication)")
    title: str = Field(..., description="Task title")
    reason: str = Field(..., description="Reason for prioritization")
    urgency: str = Field(..., description="Urgency level (e.g., critical, high, medium)")
    recommended_timeframe: str = Field(..., description="Recommended timeframe (e.g., immediate)")
    source_signals: List[str] = Field(default_factory=list, description="Supporting signals from input")


class TaskPrioritizationResponse(BaseModel):
    """Response schema for task prioritization."""
    request_id: Optional[str] = Field(None, description="Request identifier")
    prioritized_tasks: List[PrioritizedTask] = Field(
        default_factory=list,
        description="List of prioritized tasks ordered by urgency"
    )
    summary: str = Field(default="", description="Summary message")
    processing_metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Processing metadata"
    )
