"""Pydantic models for request and response schemas."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List, Any, Literal
from datetime import datetime
from app.core.constants import UserRole, TaskType, SupportedLanguage


class UserContext(BaseModel):
    """User context information."""
    user_id: str = Field(..., description="Unique identifier for the user")
    user_role: UserRole = Field(..., description="Role of the user (doctor, nurse, admin)")
    department: str = Field(..., description="Department where the user works")


class StructuredFields(BaseModel):
    """Structured medical data extracted from free text."""
    # Core clinical fields
    chief_complaint: Optional[str] = Field(None, description="Primary reason for visit")
    history_of_present_illness: Optional[str] = Field(None, description="Detailed history")
    diagnosis: Optional[List[str]] = Field(None, description="List of diagnoses")
    medications: Optional[List[Dict[str, Any]]] = Field(None, description="List of medications with details")
    vitals: Optional[Dict[str, Any]] = Field(None, description="Vital signs")
    procedures: Optional[List[str]] = Field(None, description="List of procedures performed")
    allergies: Optional[List[str]] = Field(None, description="List of allergies")
    assessment: Optional[str] = Field(None, description="Clinical assessment")
    plan: Optional[str] = Field(None, description="Treatment plan")
    
    # Additional fields that may be extracted
    past_medical_history: Optional[str] = Field(None, description="Past medical history")
    family_history: Optional[str] = Field(None, description="Family medical history")
    social_history: Optional[str] = Field(None, description="Social history")
    review_of_systems: Optional[Dict[str, str]] = Field(None, description="Review of systems by system")
    
    class Config:
        extra = "forbid"  # Reject unexpected fields


class UncertaintyFlag(BaseModel):
    """Flag indicating uncertainty or missing data."""
    field_name: str = Field(..., description="Name of the field with uncertainty")
    reason: str = Field(..., description="Reason for uncertainty")
    confidence: Optional[str] = Field(None, description="Confidence level: low, medium, high")


class ContradictionFlag(BaseModel):
    """Flag indicating contradiction between user text and patient record."""
    field_name: str = Field(..., description="Name of the field with contradiction")
    user_text_value: Any = Field(..., description="Value extracted from user text")
    patient_record_value: Any = Field(..., description="Value from patient record")
    recommendation: str = Field(..., description="Recommendation for resolution")
    severity: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Severity of the contradiction: low (minor), medium (moderate), high (critical)"
    )


class SourceTrace(BaseModel):
    """Trace information for auditability."""
    field_name: str = Field(..., description="Name of the extracted field")
    source: Literal["user_text", "patient_record", "inferred"] = Field(..., description="Source of the data")
    extraction_method: str = Field(..., description="Method used for extraction")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the extraction occurred")


class Warning(BaseModel):
    """Warning message for the user."""
    level: Literal["info", "warning", "error"] = Field(..., description="Warning level")
    message: str = Field(..., description="Warning message")
    field_name: Optional[str] = Field(None, description="Related field name if applicable")


class AutoPopulationRequest(BaseModel):
    """Request schema for auto-population task."""
    request_id: str = Field(..., description="Unique identifier for this request")
    user_context: UserContext = Field(..., description="User context information")
    input_language: SupportedLanguage = Field(default=SupportedLanguage.EN, description="Language of input text")
    output_language: SupportedLanguage = Field(default=SupportedLanguage.EN, description="Language of output")
    user_text: str = Field(..., min_length=1, max_length=10000, description="Free-text clinical input from user")
    patient_data: Dict[str, Any] = Field(..., description="Onsite patient record data")
    expected_output: List[str] = Field(..., description="List of field names expected in output")
    
    @field_validator("user_text")
    @classmethod
    def validate_user_text(cls, v: str) -> str:
        """Validate user text is not empty."""
        if not v or not v.strip():
            raise ValueError("user_text cannot be empty")
        return v.strip()
    
    @field_validator("expected_output")
    @classmethod
    def validate_expected_output(cls, v: List[str]) -> List[str]:
        """Validate expected output list is not empty."""
        if not v:
            raise ValueError("expected_output cannot be empty")
        return v


class AutoPopulationResponse(BaseModel):
    """Response schema for auto-population task."""
    request_id: str = Field(..., description="Request identifier")
    task_type: TaskType = Field(
        default=TaskType.AUTO_POPULATION,
        description="Type of task performed"
    )
    output_language: SupportedLanguage = Field(..., description="Language of output")
    structured_fields: StructuredFields = Field(..., description="Extracted structured data")
    uncertainty_flags: List[UncertaintyFlag] = Field(default_factory=list, description="Fields with uncertainty")
    contradictions: List[ContradictionFlag] = Field(default_factory=list, description="Contradictions found")
    source_trace: List[SourceTrace] = Field(default_factory=list, description="Source trace for auditability")
    warnings: List[Warning] = Field(default_factory=list, description="Warnings for the user")
    processing_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional processing metadata"
    )

