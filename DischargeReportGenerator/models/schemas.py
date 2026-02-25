"""
Pydantic models for Discharge Report Generation
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime


class PatientRecord(BaseModel):
    """Anonymized patient record."""
    patient_id: str
    age: int
    gender: str
    admission_date: str
    discharge_date: Optional[str] = None
    primary_diagnosis: str
    secondary_diagnoses: List[str] = []
    allergies: List[str] = []
    medications_on_admission: List[Dict[str, str]] = []


class ClinicalDocumentation(BaseModel):
    """Onsite clinical documentation."""
    progress_notes: List[str] = []
    admission_notes: Optional[str] = None
    prior_discharge_summaries: List[str] = []
    procedures_performed: List[Dict[str, str]] = []
    lab_results: Dict[str, Any] = {}
    imaging_results: List[Dict[str, str]] = []
    consultation_notes: List[str] = []


class ReportTemplate(BaseModel):
    """Optional report template structure."""
    template_name: str
    sections: List[str]
    required_fields: List[str] = []
    format_type: str = "standard"  # standard, detailed, brief


class DischargeReportRequest(BaseModel):
    """Request for discharge report generation."""
    patient_record: PatientRecord
    clinical_documentation: ClinicalDocumentation
    report_template: Optional[ReportTemplate] = None
    generation_mode: str = "template"  # template or freeform
    include_medications: bool = True
    include_followup: bool = True


class DischargeReportSection(BaseModel):
    """A single section of the discharge report."""
    section_name: str
    content: str
    confidence: float = 1.0
    sources: List[str] = []


class DischargeReportResponse(BaseModel):
    """Generated discharge report."""
    patient_id: str
    generation_timestamp: str
    generation_mode: str
    report_sections: List[DischargeReportSection]
    full_report_text: str
    template_used: Optional[Dict[str, Any]] = None
    confidence_score: float
    disclaimer: str
    requires_physician_review: bool = True