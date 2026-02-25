"""Clinical domain models - structured clinical summary"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class VitalTrend(BaseModel):
    """Trend data for a vital sign"""
    last: Optional[float] = Field(None, description="Most recent value")
    min: Optional[float] = Field(None, description="Minimum value in window")
    max: Optional[float] = Field(None, description="Maximum value in window")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    notable_changes: List[str] = Field(default_factory=list, description="Notable changes detected")


class InfusionStatus(BaseModel):
    """Status of a continuous infusion"""
    med_name: str = Field(..., description="Medication name")
    current_rate: Optional[str] = Field(None, description="Current rate")
    max_rate: Optional[str] = Field(None, description="Maximum rate in window")
    rate_unit: Optional[str] = Field(None, description="Rate unit")
    dose: Optional[str] = Field(None, description="Dose")
    dose_unit: Optional[str] = Field(None, description="Dose unit")


class IOStatus(BaseModel):
    """Input/Output status"""
    urine_output_total: Optional[float] = Field(None, description="Total urine output in window")
    net_balance: Optional[float] = Field(None, description="Net I/O balance")
    unit: Optional[str] = Field(None, description="Unit (typically mL)")


class SystemSummary(BaseModel):
    """Summary for a body system"""
    respiratory: Dict[str, Any] = Field(default_factory=dict, description="Respiratory system data")
    cardiovascular: Dict[str, Any] = Field(default_factory=dict, description="Cardiovascular system data")
    renal: Dict[str, Any] = Field(default_factory=dict, description="Renal system data")
    neurological: Dict[str, Any] = Field(default_factory=dict, description="Neurological system data")
    infectious_disease: Dict[str, Any] = Field(default_factory=dict, description="ID/infection data")


class ClinicalSummary(BaseModel):
    """Structured clinical summary from trend analysis"""
    patient_id: str = Field(..., description="Patient identifier")
    time_window_start: datetime = Field(..., description="Analysis window start")
    time_window_end: datetime = Field(..., description="Analysis window end")
    
    # Vitals
    heart_rate: Optional[VitalTrend] = None
    blood_pressure_systolic: Optional[VitalTrend] = None
    blood_pressure_diastolic: Optional[VitalTrend] = None
    mean_arterial_pressure: Optional[VitalTrend] = None
    temperature: Optional[VitalTrend] = None
    respiratory_rate: Optional[VitalTrend] = None
    oxygen_saturation: Optional[VitalTrend] = None
    fio2: Optional[VitalTrend] = None
    peep: Optional[VitalTrend] = None
    tidal_volume: Optional[VitalTrend] = None
    
    # Infusions
    active_infusions: List[InfusionStatus] = Field(default_factory=list)
    
    # I/O
    io_status: Optional[IOStatus] = None
    
    # Systems
    systems: SystemSummary = Field(default_factory=SystemSummary)
    
    # Additional structured data
    recent_labs: List[Dict[str, Any]] = Field(default_factory=list, description="Recent lab results")
    recent_events: List[Dict[str, Any]] = Field(default_factory=list, description="Recent clinical events")
    lines_tubes: List[Dict[str, Any]] = Field(default_factory=list, description="Lines and tubes")
    
    # Metadata
    diagnoses: Optional[List[str]] = None
    code_status: Optional[str] = None
