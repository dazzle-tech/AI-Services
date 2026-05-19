"""Pydantic request and response schemas for SepsisSentinel API."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """Request schema for sepsis analysis.

    Provide either a patient_id to use a built-in sample patient file,
    or supply raw patient_data directly.
    """

    patient_id: Optional[int] = Field(
        None,
        description="Sample patient ID (1, 2, or 3). Loads from sample_data/.",
        ge=1,
        le=3,
    )
    patient_data: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Raw patient data dict with patient_info and hourly_data keys. "
            "Use this instead of patient_id to analyse custom data."
        ),
    )


class CustomAnalysisRequest(BaseModel):
    """Request schema for creating an analysis from custom patient data."""

    patient_data: Dict[str, Any] = Field(
        ...,
        description=(
            "Raw patient data dict with patient_info and hourly_data keys."
        ),
    )


class PatientListItem(BaseModel):
    """Summary information for a single sample patient."""

    patient_id: int = Field(..., description="Patient numeric ID")
    name: str = Field(..., description="Patient name")
    admission_reason: str = Field(..., description="Reason for admission")


class PatientDetailResponse(BaseModel):
    """Full sample patient payload."""

    patient_id: int = Field(..., description="Sample patient numeric ID")
    patient_data: Dict[str, Any] = Field(
        ..., description="Complete sample patient data payload"
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service health status")
    service: str = Field(default="sepsis-sentinel")
    version: str = Field(..., description="API version")
    model: Optional[str] = Field(None, description="OpenAI model in use")
    openai_configured: bool = Field(
        ..., description="Whether the OpenAI key is configured"
    )


class AnalyzeResponse(BaseModel):
    """Response schema wrapping the full sepsis analysis result."""

    patient_id: Optional[int] = Field(
        None, description="Patient ID that was analysed"
    )
    analysis: Dict[str, Any] = Field(
        ..., description="Complete sepsis risk assessment JSON"
    )
    output_file: Optional[str] = Field(
        None, description="Path where output was saved on disk"
    )
    source: str = Field(
        ..., description="Whether the analysis used sample or custom data"
    )


class PatientListResponse(BaseModel):
    """Response containing list of available sample patients."""

    patients: List[PatientListItem] = Field(
        ..., description="Available sample patients"
    )
