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
    # ===== Roles =====
    RESIDENT_DOCTOR = "resident doctor"
    NURSE = "nurse"

    # ===== Primary Care =====
    GENERAL = "general"
    FAMILY_MEDICINE = "family medicine"
    INTERNAL_MEDICINE = "internal medicine"
    PEDIATRICS = "pediatrics"
    GERIATRICS = "geriatrics"

    # ===== Surgery =====
    GENERAL_SURGERY = "general surgery"
    CARDIOTHORACIC_SURGERY = "cardiothoracic surgery"
    NEUROSURGERY = "neurosurgery"
    ORTHOPEDIC_SURGERY = "orthopedic surgery"
    PLASTIC_RECONSTRUCTIVE_SURGERY = "plastic and reconstructive surgery"
    VASCULAR_SURGERY = "vascular surgery"
    UROLOGY = "urology"
    OTOLARYNGOLOGY_ENT = "otolaryngology (ent)"
    ORAL_MAXILLOFACIAL_SURGERY = "oral and maxillofacial surgery"
    TRAUMA_SURGERY = "trauma surgery"
    BARIATRIC_SURGERY = "bariatric surgery"
    COLORECTAL_SURGERY = "colorectal surgery"
    TRANSPLANT_SURGERY = "transplant surgery"

    # ===== Medical Specialties =====
    CARDIOLOGY = "cardiology"
    ENDOCRINOLOGY = "endocrinology"
    GASTROENTEROLOGY = "gastroenterology"
    HEMATOLOGY = "hematology"
    INFECTIOUS_DISEASE = "infectious disease"
    NEPHROLOGY = "nephrology"
    NEUROLOGY = "neurology"
    ONCOLOGY = "oncology"
    PULMONOLOGY = "pulmonology"
    RHEUMATOLOGY = "rheumatology"
    DERMATOLOGY = "dermatology"
    ALLERGY_IMMUNOLOGY = "allergy and immunology"

    # ===== ENT / Eyes =====
    OPHTHALMOLOGY = "ophthalmology"

    # ===== Diagnostics =====
    PATHOLOGY = "pathology"
    RADIOLOGY = "radiology"
    NUCLEAR_MEDICINE = "nuclear medicine"
    CLINICAL_LABORATORY_MEDICINE = "clinical laboratory medicine"

    # ===== Rehab & Pain =====
    PMR = "physical medicine and rehabilitation (pm&r)"
    PAIN_MEDICINE = "pain medicine"
    SPORTS_MEDICINE = "sports medicine"
    SLEEP_MEDICINE = "sleep medicine"

    # ===== OB / GYN =====
    OBGYN = "obstetrics and gynecology (ob/gyn)"
    MATERNAL_FETAL_MEDICINE = "maternal-fetal medicine"
    REPRODUCTIVE_ENDOCRINOLOGY_INFERTILITY = "reproductive endocrinology and infertility"
    GYNECOLOGIC_ONCOLOGY = "gynecologic oncology"

    # ===== Pediatrics Subspecialties =====
    PEDIATRIC_CARDIOLOGY = "pediatric cardiology"
    PEDIATRIC_ENDOCRINOLOGY = "pediatric endocrinology"
    PEDIATRIC_GASTROENTEROLOGY = "pediatric gastroenterology"
    PEDIATRIC_HEMATOLOGY_ONCOLOGY = "pediatric hematology/oncology"
    PEDIATRIC_NEPHROLOGY = "pediatric nephrology"
    PEDIATRIC_NEUROLOGY = "pediatric neurology"
    PEDIATRIC_PULMONOLOGY = "pediatric pulmonology"
    PEDIATRIC_INFECTIOUS_DISEASE = "pediatric infectious disease"

    # ===== Psychiatry =====
    PSYCHIATRY = "psychiatry"
    CHILD_ADOLESCENT_PSYCHIATRY = "child and adolescent psychiatry"
    FORENSIC_PSYCHIATRY = "forensic psychiatry"
    GERIATRIC_PSYCHIATRY = "geriatric psychiatry"

    # ===== Emergency & Critical =====
    EMERGENCY_MEDICINE = "emergency medicine"
    CRITICAL_CARE_MEDICINE = "critical care medicine"

    # ===== Public / Other =====
    PUBLIC_HEALTH_MEDICINE = "public health medicine"
    OCCUPATIONAL_MEDICINE = "occupational medicine"
    AEROSPACE_MEDICINE = "aerospace medicine"
    MEDICAL_GENETICS = "medical genetics"
    HOSPICE_PALLIATIVE_MEDICINE = "hospice and palliative medicine"
    LIFESTYLE_MEDICINE = "lifestyle medicine"

    # ===== Anesthesia =====
    ANESTHESIOLOGY = "anesthesiology"



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


# API 2: User Role-based Recommendations - New Input Structure
class PatientInfo(BaseModel):
    """Patient information."""
    mrn: str = Field(..., description="Medical Record Number")
    fullName: str = Field(..., description="Patient full name")
    gender: str = Field(..., description="Patient gender")
    dob: str = Field(..., description="Date of birth")


class VisitInfo(BaseModel):
    """Visit information."""
    visitId: str = Field(..., description="Visit ID")
    visitType: str = Field(..., description="Type of visit")
    plannedStartDate: str = Field(..., description="Planned start date")
    chiefComplaint: str = Field(..., description="Chief complaint")
    patientAge: str = Field(..., description="Patient age")


class DiagnosisInfo(BaseModel):
    """Diagnosis information."""
    type: str = Field(..., description="Diagnosis type")
    value: str = Field(..., description="Diagnosis value")


class MiniSummary(BaseModel):
    """Mini summary with allergies and warnings."""
    allergies: List[str] = Field(default_factory=list, description="List of allergies")
    medicalWarnings: str = Field(..., description="Medical warnings")


class UserRoleRecommendationRequest(BaseModel):
    """Request schema for user role-based recommendations with new input structure."""
    request_id: Optional[str] = Field(None, description="Optional unique identifier")
    patient: PatientInfo = Field(..., description="Patient information")
    visit: VisitInfo = Field(..., description="Visit information")
    complain: str = Field(..., description="Patient complaint")
    diagnosis: DiagnosisInfo = Field(..., description="Diagnosis information")
    practitioner: str = Field(..., description="Practitioner role and specialty (e.g., 'Role: NURSE | Specialty: RESIDENT_DOCTOR')")
    miniSummary: MiniSummary = Field(..., description="Mini summary with allergies and warnings")

