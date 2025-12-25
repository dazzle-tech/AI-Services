"""Pydantic models for request and response schemas."""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List, Any
from enum import Enum


class RecommendationType(str, Enum):
    """Types of clinical recommendations."""
    MEDICAL = "medical"  # Default type - always use this
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


class MedicalSpecialty(str, Enum):
    """Medical specialties."""
    CARDIOLOGY = "cardiology"
    ENDOCRINOLOGY = "endocrinology"
    NEUROLOGY = "neurology"
    ONCOLOGY = "oncology"
    PEDIATRICS = "pediatrics"
    PSYCHIATRY = "psychiatry"
    PULMONOLOGY = "pulmonology"
    GASTROENTEROLOGY = "gastroenterology"
    NEPHROLOGY = "nephrology"
    RHEUMATOLOGY = "rheumatology"
    DERMATOLOGY = "dermatology"
    ORTHOPEDICS = "orthopedics"
    GENERAL = "general"


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


# API 1: Specialty-based Consultation Request
class SpecialtyConsultationRequest(BaseModel):
    """Request schema for specialty-based consultation recommendations."""
    request_id: Optional[str] = Field(None, description="Optional unique identifier")
    specialty: MedicalSpecialty = Field(..., description="Selected medical specialty")
    patient_context: Optional[PatientContextInput] = Field(None, description="Optional patient context for personalized recommendations")
    complaint: Optional[str] = Field(None, description="Patient's chief complaint or reason for consultation")


class SpecialtyConsultationResponse(BaseModel):
    """Response schema for specialty consultation - returns only summary."""
    request_id: Optional[str] = Field(None, description="Request identifier")
    summary: str = Field(..., description="Concise summary containing all recommendations")
    processing_metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Processing metadata"
    )


# API 2: User Role-based Recommendations
class UserRoleRecommendationRequest(BaseModel):
    """Request schema for user role-based recommendations."""
    request_id: Optional[str] = Field(None, description="Optional unique identifier")
    user_role: MedicalSpecialty = Field(..., description="User's medical specialty/role")
    patient_context: PatientContextInput = Field(..., description="Complete patient context data")
    complaint: Optional[str] = Field(None, description="Patient's chief complaint")
    focus_areas: Optional[List[str]] = Field(
        None,
        description="Specific areas to focus on"
    )

