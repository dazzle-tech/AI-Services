"""Pydantic models for request and response schemas - Version 2 (Clean API Contract)."""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, Dict, List, Any, Literal
from datetime import datetime
from app.core.constants import UserRole, TaskType, SupportedLanguage


# Reuse existing models
from app.models.schemas import (
    StructuredFields,
    UncertaintyFlag,
    Warning
)


class User(BaseModel):
    """User information."""
    user_id: str = Field(..., description="Unique identifier for the user")
    role: UserRole = Field(..., description="Role of the user (doctor, nurse, admin)")
    department: str = Field(..., description="Department where the user works")


class Languages(BaseModel):
    """Input and output language specification."""
    input: SupportedLanguage = Field(default=SupportedLanguage.EN, description="Language of input text")
    output: SupportedLanguage = Field(default=SupportedLanguage.EN, description="Language of output")


class DocumentReference(BaseModel):
    """Reference to a document in the patient record."""
    doc_id: str = Field(..., description="Document identifier")
    doc_type: str = Field(
        ...,
        description="Type of document: 'patient_history', 'progress_note', 'lab_results', 'imaging', 'discharge_summary', etc."
    )


class OnsiteData(BaseModel):
    """Onsite patient record data."""
    patient_record_id: Optional[str] = Field(None, description="Patient record identifier")
    is_deidentified: bool = Field(default=False, description="Whether the data is de-identified")
    documents: List[DocumentReference] = Field(default_factory=list, description="List of document references")
    # For backward compatibility, allow raw patient data
    patient_data: Optional[Dict[str, Any]] = Field(None, description="Raw patient data (if not using record_id)")
    
    def get_patient_data_dict(self) -> Dict[str, Any]:
        """Get patient data as dictionary."""
        if self.patient_data:
            return self.patient_data
        # If using record_id, return empty dict (would be fetched from database in production)
        return {}


class Inputs(BaseModel):
    """Input data for the request."""
    user_text: str = Field(..., min_length=1, max_length=10000, description="Free-text clinical input from user")
    onsite: OnsiteData = Field(..., description="Onsite patient record data")
    
    @field_validator("user_text")
    @classmethod
    def validate_user_text(cls, v: str) -> str:
        """Validate user text is not empty."""
        if not v or not v.strip():
            raise ValueError("user_text cannot be empty")
        return v.strip()


class RequestedOutputs(BaseModel):
    """Specification of what outputs are requested."""
    include_summary: bool = Field(default=False, description="Include a summary of the clinical note")
    include_structured_fields: bool = Field(default=True, description="Include structured field extraction")
    include_vitals: bool = Field(default=True, description="Include vital signs extraction")
    include_quality_indicators: bool = Field(default=False, description="Include quality indicators (uncertainty flags, contradictions, warnings)")
    include_trace: bool = Field(default=False, description="Include source trace information")
    
    @field_validator("include_structured_fields", "include_vitals")
    @classmethod
    def validate_at_least_one(cls, v: bool, info) -> bool:
        """Ensure at least one output type is requested."""
        # This will be checked at the request level
        return v


class OutputSchema(BaseModel):
    """Output schema specification."""
    structured_fields_template: str = Field(
        default="v1_clinical_note_fields",
        description="Template for structured fields schema"
    )


class AutoPopulationRequestV2(BaseModel):
    """Request schema for auto-population task (Version 2 - Clean API Contract)."""
    request_id: str = Field(..., description="Unique identifier for this request")
    task_type: Literal[TaskType.AUTO_POPULATION] = Field(
        default=TaskType.AUTO_POPULATION,
        description="Type of task"
    )
    user: User = Field(..., description="User information")
    languages: Languages = Field(default_factory=Languages, description="Input and output languages")
    inputs: Inputs = Field(..., description="Input data")
    requested_outputs: RequestedOutputs = Field(..., description="Requested output types")
    output_schema: Optional[OutputSchema] = Field(default_factory=OutputSchema, description="Output schema specification")
    
    def get_expected_fields(self) -> List[str]:
        """
        Get list of expected field names based on requested outputs.
        Only includes fields that are actually needed for the requested outputs.
        If only vitals is requested, only extract vitals (summary can be generated from user text).
        """
        expected = []
        
        if self.requested_outputs.include_structured_fields:
            # Add core structured fields that are commonly present
            expected.extend([
                "chief_complaint", "history_of_present_illness", "diagnosis",
                "medications", "allergies", "assessment", "plan",
                "past_medical_history"
            ])
        
        if self.requested_outputs.include_vitals:
            expected.append("vitals")
        
        # If only summary + vitals (no structured_fields), only extract vitals
        # Summary will be generated from user text, not from extracted structured fields
        # This ensures we don't extract unnecessary fields
        
        return expected
    
    def get_patient_data_dict(self) -> Dict[str, Any]:
        """Get patient data as dictionary for backward compatibility."""
        if self.inputs.onsite.patient_data:
            return self.inputs.onsite.patient_data
        # If using record_id, return empty dict (would be fetched from database in production)
        return {}


class ContradictionFlagV2(BaseModel):
    """Flag indicating contradiction between user text and patient record (Version 2)."""
    field_name: str = Field(..., description="Name of the field with contradiction")
    user_text_value: Any = Field(..., description="Value extracted from user text")
    patient_record_value: Any = Field(..., description="Value from patient record")
    recommendation: str = Field(..., description="Recommendation for resolution")
    severity: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Severity of the contradiction"
    )
    confidence: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Confidence in the contradiction detection"
    )


class SourceTraceV2(BaseModel):
    """Trace information for auditability (Version 2)."""
    field_name: str = Field(..., description="Name of the extracted field")
    source: Literal["user_text", "patient_record", "inferred"] = Field(..., description="Source of the data")
    extraction_method: str = Field(..., description="Method used for extraction")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the extraction occurred")


class Outputs(BaseModel):
    """Output data."""
    summary: Optional[str] = Field(None, description="Summary of the clinical note")
    structured_fields: Optional[StructuredFields] = Field(None, description="Extracted structured data")
    vitals: Optional[Dict[str, Any]] = Field(None, description="Vital signs (if requested separately)")


class Quality(BaseModel):
    """Quality indicators for the extraction."""
    uncertainty_flags: List[UncertaintyFlag] = Field(default_factory=list, description="Fields with uncertainty")
    contradictions: List[ContradictionFlagV2] = Field(default_factory=list, description="Contradictions found")
    warnings: List[Warning] = Field(default_factory=list, description="Warnings for the user")


class Trace(BaseModel):
    """Trace information for auditability."""
    source_trace: List[SourceTraceV2] = Field(default_factory=list, description="Source trace for auditability")


class Metadata(BaseModel):
    """Processing metadata."""
    model_config = ConfigDict(
        protected_namespaces=()
    )

    model_used: str = Field(..., description="AI model used for processing")
    processing_timestamp: datetime = Field(default_factory=datetime.utcnow, description="When processing occurred")
    user_role: str = Field(..., description="User role")
    department: str = Field(..., description="Department")
    schema_version: str = Field(default="auto_population.v1", description="Schema version")


class AutoPopulationResponseV2(BaseModel):
    """Response schema for auto-population task (Version 2 - Clean API Contract)."""
    model_config = ConfigDict(
        # Exclude None fields from JSON serialization, but keep outputs fields
        exclude_none=True
    )
    
    def model_dump(self, **kwargs):
        """Override to ensure vitals are included when requested, even if None."""
        data = super().model_dump(**kwargs)
        # If outputs.vitals is explicitly requested, include it even if None
        # (This is handled by the service layer setting vitals to a dict, not None)
        return data
    
    request_id: str = Field(..., description="Request identifier")
    task_type: Literal[TaskType.AUTO_POPULATION] = Field(
        default=TaskType.AUTO_POPULATION,
        description="Type of task performed"
    )
    outputs: Outputs = Field(..., description="Output data")
    quality: Optional[Quality] = Field(None, description="Quality indicators (optional)")
    trace: Optional[Trace] = Field(None, description="Trace information (optional)")
    metadata: Metadata = Field(..., description="Processing metadata")

