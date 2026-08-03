"""Domain entities for discharge QA service."""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class PatientRecord(BaseModel):
    """Anonymized patient record."""
    age: Optional[int] = None
    sex: Optional[str] = None
    admission_date: Optional[str] = None
    discharge_date: Optional[str] = None
    diagnoses: List[str] = Field(default_factory=list)
    medications: List[Dict[str, Any]] = Field(default_factory=list)
    medications_on_admission: List[Dict[str, Any]] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    procedures: List[str] = Field(default_factory=list)
    vitals: Optional[Dict[str, Any]] = None
    additional_data: Dict[str, Any] = Field(default_factory=dict)


class OnsiteDoc(BaseModel):
    """Clinical document from onsite system."""
    doc_id: str
    doc_type: str  # history_and_physical, progress_note, etc.
    timestamp: str  # ISO 8601
    department: str
    content: Any  # text or JSON
    is_deidentified: bool = True


class DischargeReport(BaseModel):
    """Discharge report input."""
    content: Any  # text or JSON
    format: str = "text"  # "text" or "json"


class ReportTemplate(BaseModel):
    """Template defining required sections/fields."""
    sections: List[Dict[str, Any]] = Field(default_factory=list)
    required_fields: Dict[str, List[str]] = Field(default_factory=dict)
    section_order: List[str] = Field(default_factory=list)


class QualityRules(BaseModel):
    """Quality validation rules."""
    completeness: Dict[str, Any] = Field(default_factory=dict)
    consistency: Dict[str, Any] = Field(default_factory=dict)
    safety: Dict[str, Any] = Field(default_factory=dict)
    structure: Dict[str, Any] = Field(default_factory=dict)

