"""Pydantic models for request and response schemas."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List, Any, Union


class SurgeryWithStatus(BaseModel):
    """A surgery with completion status."""
    name: str = Field(..., description="Surgery name or procedure (e.g., 'Appendectomy 2010')")
    status: str = Field(
        default="completed",
        description="Surgery status (e.g. completed, scheduled, or any other value)"
    )


def _normalize_surgery(item: Union[str, Dict[str, Any], SurgeryWithStatus]) -> SurgeryWithStatus:
    """Accept string, dict, or SurgeryWithStatus; return SurgeryWithStatus."""
    if isinstance(item, SurgeryWithStatus):
        return item
    if isinstance(item, str):
        return SurgeryWithStatus(name=item, status="completed")
    if isinstance(item, dict):
        return SurgeryWithStatus(
            name=item.get("name", ""),
            status=item.get("status", "completed"),
        )
    raise ValueError(f"Invalid surgery item: {item}")


class PatientDataInput(BaseModel):
    """Input schema for patient data."""
    # Age is a single string field (e.g. "5 years", "3 months", "2 days", "35")
    Age: str = Field(..., description="Patient age as a string (e.g., '45 years', '3 months', '2 days')")
    Gender: str = Field(..., description="Patient gender")
    Diagnosis: str = Field(..., description="Primary diagnosis")
    Symptoms: List[str] = Field(default_factory=list, description="List of symptoms")
    Medications: List[str] = Field(default_factory=list, description="List of medications")
    Surgeries: List[SurgeryWithStatus] = Field(
        default_factory=list,
        description="List of surgeries with status: completed or scheduled (each item: string or {name, status})"
    )

    @field_validator("Surgeries", mode="before")
    @classmethod
    def normalize_surgeries(cls, v: Any) -> List[SurgeryWithStatus]:
        """Accept list of strings or list of {name, status}; normalize to List[SurgeryWithStatus]."""
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return [_normalize_surgery(item) for item in v]
    Allergies: List[str] = Field(default_factory=list, description="List of allergies")
    Medical_Warnings: List[str] = Field(default_factory=list, description="List of medical warnings")
    Problems: List[str] = Field(default_factory=list, description="List of comorbidities/problems")
    Vitals: Dict[str, str] = Field(default_factory=dict, description="Vital signs as key-value pairs")
    Lab_Results: Dict[str, Any] = Field(default_factory=dict, description="Recent lab results (e.g., Troponin, HbA1c, Creatinine)")
    
    @field_validator("Age")
    @classmethod
    def validate_age(cls, v: str) -> str:
        """Validate age is not empty."""
        if not v or not v.strip():
            raise ValueError("Age cannot be empty")
        return v.strip()
    
    @field_validator("Gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        """Validate gender is not empty."""
        if not v or not v.strip():
            raise ValueError("Gender cannot be empty")
        return v.strip()
    
    @field_validator("Diagnosis")
    @classmethod
    def validate_diagnosis(cls, v: str) -> str:
        """Validate diagnosis is not empty."""
        if not v or not v.strip():
            raise ValueError("Diagnosis cannot be empty")
        return v.strip()


class SummaryRequest(BaseModel):
    """Request schema for clinical summary generation."""
    request_id: Optional[str] = Field(None, description="Optional unique identifier for this request")
    patient_data: PatientDataInput = Field(..., description="Patient data to summarize")


class SummaryResponse(BaseModel):
    """Response schema for clinical summary generation."""
    request_id: Optional[str] = Field(None, description="Request identifier")
    ClinicalSummary: str = Field(..., description="Generated clinical summary")
    processing_metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional processing metadata"
    )

