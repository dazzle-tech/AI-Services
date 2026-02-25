"""All incoming request models - MANDATORY location for API layer imports"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class PatientInfo(BaseModel):
    """Patient identification and demographics"""
    id: str = Field(..., description="Patient identifier")
    name: Optional[str] = Field(None, description="Patient name")
    age: Optional[int] = Field(None, ge=0, le=150, description="Patient age in years")
    sex: Optional[str] = Field(None, description="Patient sex")
    mrn: Optional[str] = Field(None, description="Medical record number")


class EncounterInfo(BaseModel):
    """Encounter/hospitalization information"""
    id: str = Field(..., description="Encounter identifier")
    admit_time: Optional[datetime] = Field(None, description="Admission timestamp (ISO format)")
    icu_day: Optional[int] = Field(None, ge=0, description="Day number in ICU")


class TimeWindow(BaseModel):
    """Time window for data analysis"""
    start: datetime = Field(..., description="Start timestamp (ISO format)")
    end: datetime = Field(..., description="End timestamp (ISO format)")

    @field_validator('end')
    @classmethod
    def validate_time_window(cls, v, info):
        """Ensure end is after start"""
        if 'start' in info.data and v <= info.data['start']:
            raise ValueError("end must be after start")
        return v


class FlowsheetEntry(BaseModel):
    """Single flowsheet data point"""
    timestamp: datetime = Field(..., description="Measurement timestamp (ISO format)")
    item_code: Optional[str] = Field(None, description="Item code/identifier")
    item_name: str = Field(..., description="Item name/description")
    value: str = Field(..., description="Value as string (to handle various formats)")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    source: Optional[str] = Field(None, description="Data source")


class MedicationEntry(BaseModel):
    """Medication administration record"""
    timestamp: datetime = Field(..., description="Administration timestamp (ISO format)")
    med_name: str = Field(..., description="Medication name")
    dose: Optional[str] = Field(None, description="Dose amount")
    dose_unit: Optional[str] = Field(None, description="Dose unit")
    route: Optional[str] = Field(None, description="Administration route")
    is_infusion: bool = Field(False, description="Whether this is a continuous infusion")
    rate: Optional[str] = Field(None, description="Infusion rate")
    rate_unit: Optional[str] = Field(None, description="Rate unit")


class LabEntry(BaseModel):
    """Laboratory result"""
    timestamp: datetime = Field(..., description="Lab result timestamp (ISO format)")
    lab_name: str = Field(..., description="Laboratory test name")
    value: str = Field(..., description="Lab value as string")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    ref_range: Optional[str] = Field(None, description="Reference range")


class EventEntry(BaseModel):
    """Clinical event or note"""
    timestamp: datetime = Field(..., description="Event timestamp (ISO format)")
    type: str = Field(..., description="Event type/category")
    description: str = Field(..., description="Event description")


class LineTubeInfo(BaseModel):
    """Lines, tubes, and devices"""
    name: str = Field(..., description="Line/tube name (e.g., 'Central Line', 'ETT')")
    status: Optional[str] = Field(None, description="Status (e.g., 'in place', 'removed')")
    inserted_time: Optional[datetime] = Field(None, description="Insertion timestamp (ISO format)")


class ICURequestPayload(BaseModel):
    """Root request model for ICU summarization"""
    patient: PatientInfo = Field(..., description="Patient information")
    encounter: EncounterInfo = Field(..., description="Encounter information")
    time_window: TimeWindow = Field(..., description="Time window for analysis")
    flowsheet: List[FlowsheetEntry] = Field(default_factory=list, description="Flowsheet data points")
    meds: List[MedicationEntry] = Field(default_factory=list, description="Medication records")
    labs: List[LabEntry] = Field(default_factory=list, description="Laboratory results")
    events: List[EventEntry] = Field(default_factory=list, description="Clinical events")
    lines_tubes: List[LineTubeInfo] = Field(default_factory=list, description="Lines and tubes")
    diagnoses: Optional[List[str]] = Field(None, description="List of diagnoses")
    code_status: Optional[str] = Field(None, description="Code status (e.g., 'Full Code', 'DNR')")
