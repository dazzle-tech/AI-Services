"""Pydantic models for request and response schemas."""
from typing import Optional, Dict, List, Any, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class PatientContext(BaseModel):
    """Optional patient context for interpretation."""

    patient_id: Optional[str] = Field(None, description="Patient identifier")
    age: Optional[Union[int, str]] = Field(None, description="Patient age in years or a free-text age description")
    sex: Optional[str] = Field(None, description="Patient sex (e.g., male, female)")
    known_conditions: List[str] = Field(default_factory=list, description="Known medical conditions")
    medications: List[Union[str, Dict[str, Any]]] = Field(
        default_factory=list,
        description="Current medications as names or structured medication objects"
    )
    clinical_context: Optional[str] = Field(None, description="Clinical presentation or context")


class LabResultItem(BaseModel):
    """Single lab result with value, unit, reference range, and flag."""

    name: str = Field(..., description="Lab name (e.g., WBC, CRP, Creatinine)")
    value: str = Field(..., description="Lab value as string")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    reference_range: Optional[str] = Field(None, description="Reference range (e.g., 4.0-11.0)")
    flag: Optional[str] = Field(None, description="Flag: normal, high, low, critical")
    timestamp: Optional[str] = Field(None, description="ISO timestamp when lab was drawn")


class LabInterpretationRequest(BaseModel):
    """Request schema for lab result interpretation."""

    request_id: Optional[str] = Field(None, description="Optional unique identifier for this request")
    patient_context: Optional[PatientContext] = Field(None, description="Optional patient context")
    medications: List[Union[str, Dict[str, Any]]] = Field(
        default_factory=list,
        description="Current medications as names or structured medication objects"
    )
    lab_results: List[LabResultItem] = Field(
        default_factory=list,
        description="Current lab results to interpret"
    )
    historical_lab_results: List[LabResultItem] = Field(
        default_factory=list,
        description="Historical lab results for trend analysis"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_top_level_medications(cls, data: Any) -> Any:
        """Copy top-level medications into patient_context when provided."""
        if isinstance(data, dict):
            normalized = dict(data)
            medications = normalized.get("medications")
            patient_context = normalized.get("patient_context")

            if medications and isinstance(medications, list) and not patient_context:
                normalized["patient_context"] = {"medications": medications}
            elif medications and isinstance(medications, list) and isinstance(patient_context, dict):
                normalized_patient_context = dict(patient_context)
                if not normalized_patient_context.get("medications"):
                    normalized_patient_context["medications"] = medications
                    normalized["patient_context"] = normalized_patient_context

            return normalized

        return data

    @field_validator("lab_results")
    @classmethod
    def lab_results_not_empty(cls, v: List[LabResultItem]) -> List[LabResultItem]:
        """Lab results list must not be empty."""
        if not v or len(v) == 0:
            raise ValueError("At least one lab result is required")
        return v


class LabPattern(BaseModel):
    """Clinically meaningful pattern identified from labs."""

    label: str = Field(..., description="Pattern label (e.g., possible_infection_or_inflammation)")
    reason: str = Field(..., description="Brief explanation of the pattern")


class LabKeyFinding(BaseModel):
    """Traceable key finding tied to a specific lab result."""

    lab_name: Optional[str] = Field(None, description="Lab name")
    value: Optional[str] = Field(None, description="Exact lab value from input")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    reference_range: Optional[str] = Field(None, description="Reference range from input")
    flag: Optional[str] = Field(None, description="Flag from input such as normal, high, low, or critical")
    timestamp: Optional[str] = Field(None, description="ISO timestamp when lab was drawn")
    finding: str = Field(default="", description="Short finding text grounded in the input data")

    @model_validator(mode="before")
    @classmethod
    def coerce_legacy_finding(cls, data: Any) -> Any:
        """Allow legacy string findings while normalizing to the structured shape."""
        if isinstance(data, str):
            return {"finding": data}

        if isinstance(data, dict):
            normalized = dict(data)
            normalized["finding"] = str(
                normalized.get("finding")
                or normalized.get("text")
                or normalized.get("summary")
                or ""
            )
            return normalized

        return data


class LabTrend(BaseModel):
    """Trend identified from current vs historical values."""

    lab_name: str = Field(..., description="Lab name")
    direction: str = Field(..., description="Trend direction: rising, falling, or stable")
    summary: str = Field(default="", description="Brief summary of the trend")
    from_value: Optional[str] = Field(None, description="Starting lab value for the trend")
    to_value: Optional[str] = Field(None, description="Ending lab value for the trend")
    from_timestamp: Optional[str] = Field(None, description="Timestamp for the starting value")
    to_timestamp: Optional[str] = Field(None, description="Timestamp for the ending value")
    unit: Optional[str] = Field(None, description="Unit of measurement")

    @model_validator(mode="before")
    @classmethod
    def coerce_legacy_trend(cls, data: Any) -> Any:
        """Allow older trend payloads while exposing the expanded schema."""
        if isinstance(data, dict):
            normalized = dict(data)
            normalized.setdefault("summary", "")
            normalized.setdefault("from_value", None)
            normalized.setdefault("to_value", None)
            normalized.setdefault("from_timestamp", None)
            normalized.setdefault("to_timestamp", None)
            normalized.setdefault("unit", None)
            return normalized

        return data


class LabInterpretation(BaseModel):
    """Structured interpretation output."""

    severity: str = Field(..., description="Overall severity: low, moderate, high, or critical")
    key_findings: List[LabKeyFinding] = Field(
        default_factory=list,
        description="Key findings with traceable raw lab data"
    )
    patterns: List[LabPattern] = Field(default_factory=list, description="Clinically meaningful patterns")
    trends: List[LabTrend] = Field(
        default_factory=list,
        description="Trends from historical comparison with raw from/to values"
    )
    follow_up_considerations: List[str] = Field(
        default_factory=list,
        description="Suggested clinical follow-up considerations"
    )
    disclaimer: str = Field(
        default="This output is interpretation support and not a diagnosis.",
        description="Disclaimer that this is support, not diagnosis"
    )


class LabInterpretationResponse(BaseModel):
    """Response schema for lab result interpretation."""

    request_id: Optional[str] = Field(None, description="Request identifier")
    interpretation: LabInterpretation = Field(..., description="Structured interpretation")
    summary: str = Field(..., description="Brief summary message")
    processing_metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional processing metadata"
    )
