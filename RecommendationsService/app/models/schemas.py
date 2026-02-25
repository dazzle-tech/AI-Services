"""Pydantic models for request and response schemas."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List, Any
from enum import Enum


class SurgeryWithStatus(BaseModel):
    """A surgery with completion status."""
    name: str = Field(..., description="Surgery name or procedure (e.g., 'Appendectomy 2010')")
    status: str = Field(
        default="completed",
        description="Surgery status (e.g. completed, scheduled, or any other value)"
    )


class RecommendationType(str, Enum):
    """Types of clinical recommendations."""
    MEDICATION = "medication"
    DIAGNOSTIC = "diagnostic"
    TREATMENT = "treatment"
    MONITORING = "monitoring"
    LIFESTYLE = "lifestyle"
    REFERRAL = "referral"
    GENERAL = "general"


class RecommendationPriority(str, Enum):
    """Priority levels for recommendations."""
    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    ROUTINE = "routine"


class PatientContextInput(BaseModel):
    """Input schema for patient context."""
    age: str = Field(..., description="Patient age (e.g., '45 years', '3 months')")
    gender: str = Field(..., description="Patient gender")
    diagnosis: str = Field(..., description="Primary or working diagnosis")
    symptoms: List[str] = Field(default_factory=list, description="Current symptoms")
    medications: List[str] = Field(default_factory=list, description="Current medications")
    allergies: List[str] = Field(default_factory=list, description="Known allergies")
    comorbidities: List[str] = Field(default_factory=list, description="Comorbidities")
    vitals: Dict[str, str] = Field(default_factory=dict, description="Vital signs")
    lab_results: Dict[str, Any] = Field(default_factory=dict, description="Recent lab results")
    surgeries: List[SurgeryWithStatus] = Field(
        default_factory=list,
        description="List of surgeries with status: completed or scheduled"
    )
    clinical_notes: Optional[str] = Field(None, description="Additional clinical notes")
    
    @field_validator("age")
    @classmethod
    def validate_age(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Age cannot be empty")
        return v.strip()
    
    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Gender cannot be empty")
        return v.strip()
    
    @field_validator("diagnosis")
    @classmethod
    def validate_diagnosis(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Diagnosis cannot be empty")
        return v.strip()


class RecommendationRequest(BaseModel):
    """Request schema for clinical recommendations."""
    request_id: Optional[str] = Field(None, description="Optional unique identifier")
    patient_context: PatientContextInput = Field(..., description="Patient context data")
    recommendation_types: List[RecommendationType] = Field(
        default_factory=lambda: [RecommendationType.GENERAL],
        description="Types of recommendations requested"
    )
    focus_areas: Optional[List[str]] = Field(
        None,
        description="Specific areas to focus on (e.g., 'medication optimization', 'diagnostic workup')"
    )


class ClinicalRecommendation(BaseModel):
    """A single clinical recommendation."""
    recommendation_id: str = Field(..., description="Unique identifier for this recommendation")
    type: RecommendationType = Field(..., description="Type of recommendation")
    title: str = Field(..., description="Short title/heading")
    description: str = Field(..., description="Detailed recommendation description")
    rationale: str = Field(..., description="Clinical reasoning behind the recommendation")
    priority: RecommendationPriority = Field(..., description="Priority level")
    actionable_steps: List[str] = Field(default_factory=list, description="Specific actionable steps")
    evidence_level: Optional[str] = Field(None, description="Level of evidence (if applicable)")
    contraindications: List[str] = Field(default_factory=list, description="Any contraindications to consider")
    monitoring_requirements: Optional[str] = Field(None, description="Monitoring needed")
    follow_up: Optional[str] = Field(None, description="Follow-up recommendations")


class RecommendationsResponse(BaseModel):
    """Response schema for clinical recommendations."""
    request_id: Optional[str] = Field(None, description="Request identifier")
    patient_id: Optional[str] = Field(None, description="Patient identifier if provided")
    recommendations: List[ClinicalRecommendation] = Field(..., description="List of recommendations")
    summary: str = Field(..., description="Summary of all recommendations")
    total_recommendations: int = Field(..., description="Total number of recommendations")
    priority_breakdown: Dict[str, int] = Field(..., description="Count of recommendations by priority")
    processing_metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Processing metadata"
    )


class SpecialtyConsultationRequest(BaseModel):
    """Request for general specialty-based consultation recommendations."""
    request_id: Optional[str] = Field(None, description="Optional unique identifier")
    specialty: str = Field(..., description="Medical specialty (e.g., 'cardiology', 'pulmonology')")
    patient_context: Optional[PatientContextInput] = Field(None, description="Optional patient context")
    complaint: Optional[str] = Field(None, description="Optional chief complaint")


class ConsultationAction(BaseModel):
    """A single actionable step from a specialty consultation."""
    title: str = Field(..., description="Short action title")
    description: Optional[str] = Field(None, description="What to do and why")
    category: Optional[str] = Field(None, description="e.g. diagnostic, treatment, monitoring, follow_up")
    priority: Optional[str] = Field(None, description="e.g. high, moderate, routine")


class SpecialtyConsultationResponse(BaseModel):
    """Response with set of actions and summary from specialty consultation."""
    request_id: Optional[str] = Field(None, description="Request identifier")
    summary: str = Field(..., description="Concise summary of recommendations")
    actions: List[ConsultationAction] = Field(
        default_factory=list,
        description="Ordered set of actions considering full patient context (diagnostics, treatment, monitoring, follow-up)"
    )


class UserRoleRecommendationRequest(BaseModel):
    """Request for recommendations from the logged-in user's specialty/role perspective."""
    request_id: Optional[str] = Field(None, description="Optional unique identifier")
    user_role: str = Field(..., description="User's medical specialty/role (e.g., 'cardiology')")
    patient_context: PatientContextInput = Field(..., description="Patient context data")
    recommendation_types: List[RecommendationType] = Field(
        default_factory=lambda: [RecommendationType.GENERAL],
        description="Types of recommendations requested"
    )
    focus_areas: Optional[List[str]] = Field(None, description="Specific areas to focus on")

