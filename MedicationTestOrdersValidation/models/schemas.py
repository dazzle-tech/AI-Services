from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime


class Patient(BaseModel):
    """Patient information model"""
    mrn: str = Field(..., description="Medical Record Number")
    fullName: str = Field(..., description="Patient full name")
    gender: Optional[str] = Field("Unknown", description="Patient gender (null/empty treated as Unknown)")
    dob: str = Field(..., description="Date of birth (YYYY-MM-DD)")

    @validator('gender', pre=True)
    def normalize_gender(cls, v):
        """Accept null, empty, or missing; coerce to 'Unknown' then validate."""
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return 'Unknown'
        s = v.strip() if isinstance(v, str) else v
        allowed = ['Male', 'Female', 'Other', 'Unknown']
        if s not in allowed:
            return 'Unknown'
        return s


class Encounter(BaseModel):
    """Encounter/visit information model"""
    visitId: str = Field(..., description="Visit identifier")
    visitType: str = Field(..., description="Type of visit")
    plannedStartDate: str = Field(..., description="Planned start date")
    chiefComplaint: Optional[str] = Field("", description="Chief complaint (null/empty allowed)")
    patientAge: str = Field(..., description="Patient age (formatted)")
    primaryDiagnosis: str = Field(..., description="Primary diagnosis with ICD code")

    @validator('chiefComplaint', pre=True)
    def normalize_chief_complaint(cls, v):
        """Accept null or missing; coerce to empty string."""
        if v is None:
            return ""
        return v if isinstance(v, str) else str(v)


class Diagnosis(BaseModel):
    """Diagnosis information model"""
    type: str = Field(..., description="Type of diagnosis")
    value: str = Field(..., description="Diagnosis code and description")


class MedicationValidationRequest(BaseModel):
    """Request model for medication validation"""
    patient: Patient
    encounter: Encounter
    listOfDiagnosis: List[Diagnosis] = Field(..., description="List of diagnosis objects outside the encounter")
    medications: List[str] = Field(..., description="List of medications to validate")

    @validator("medications", each_item=True)
    def validate_medication_entry(cls, value):
        """Require active ingredients while allowing an empty medication name."""
        if not isinstance(value, str):
            raise ValueError("Each medication entry must be a string")

        normalized = value.strip()
        if not normalized:
            raise ValueError("Medication entry cannot be empty")

        if "Active Ingredients:" not in normalized:
            raise ValueError("Each medication entry must include 'Active Ingredients:'")

        _, active_ingredients = normalized.split("Active Ingredients:", 1)
        if not active_ingredients.strip():
            raise ValueError("Active ingredients value cannot be empty")

        return value

    class Config:
        json_schema_extra = {
            "example": {
                "patient": {
                    "mrn": "1000",
                    "fullName": "John Doe",
                    "gender": "Male",
                    "dob": "2022-02-02"
                },
                "encounter": {
                    "visitId": "160",
                    "visitType": "Urgent Visit",
                    "plannedStartDate": "2025-12-24",
                    "chiefComplaint": "Chest pain",
                    "patientAge": "3y 10m 22d",
                    "primaryDiagnosis": "I20.0,Unstable angina"
                },
                "listOfDiagnosis": [
                    {
                        "type": "Encounter Diagnosis",
                        "value": "I20.0,Unstable angina"
                    }
                ],
                "medications": [
                    "Medication Name:  | Active Ingredients: Acetylsalicylic acid - 100 mg"
                ]
            }
        }


class TestValidationRequest(BaseModel):
    """Request model for test validation"""
    patient: Patient
    encounter: Encounter
    listOfDiagnosis: List[Diagnosis] = Field(..., description="List of diagnosis objects outside the encounter")
    tests: List[str] = Field(..., description="List of tests to validate")

    class Config:
        json_schema_extra = {
            "example": {
                "patient": {
                    "mrn": "1000",
                    "fullName": "John Doe",
                    "gender": "Male",
                    "dob": "2022-02-02"
                },
                "encounter": {
                    "visitId": "160",
                    "visitType": "Urgent Visit",
                    "plannedStartDate": "2025-12-24",
                    "chiefComplaint": "Chest pain",
                    "patientAge": "3y 10m 22d",
                    "primaryDiagnosis": "I20.0,Unstable angina"
                },
                "listOfDiagnosis": [
                    {
                        "type": "Encounter Diagnosis",
                        "value": "I20.0,Unstable angina"
                    }
                ],
                "tests": [
                    "Order Type: Laboratory | Test Name: Troponin | Internal Code: TROP00 | Status: New"
                ]
            }
        }


class DetailedValidation(BaseModel):
    """Detailed validation finding"""
    item: str = Field(..., description="Medication or test being validated")
    severity: str = Field(..., description="Severity level: critical, high, moderate, low, info")
    issue: str = Field(..., description="Description of the issue")
    recommendation: str = Field(..., description="Recommended action")
    evidence: Optional[str] = Field(None, description="Clinical evidence or reasoning")


class RecommendedAlternative(BaseModel):
    """Recommended alternative medication or test"""
    original_item: str = Field(..., description="Original medication or test")
    alternative: str = Field(..., description="Suggested alternative")
    rationale: str = Field(..., description="Reason for recommendation")


class QuickSummary(BaseModel):
    """Quick summary of validation results"""
    overall_status: str = Field(..., description="SAFE, CAUTION, or CONTRAINDICATED")
    top_priority: str = Field(..., description="Most critical issue if any")
    
    @validator('overall_status')
    def validate_status(cls, v):
        allowed = ['SAFE', 'CAUTION', 'CONTRAINDICATED']
        if v not in allowed:
            raise ValueError(f"Status must be one of {allowed}")
        return v


class ValidationResponse(BaseModel):
    """Response model for validation results"""
    quick_summary: QuickSummary
    detailed_validations: List[DetailedValidation]
    recommended_alternatives: List[RecommendedAlternative]
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    
    class Config:
        json_schema_extra = {
            "example": {
                "quick_summary": {
                    "overall_status": "CAUTION",
                    "top_priority": "Age-inappropriate dosing detected"
                },
                "detailed_validations": [
                    {
                        "item": "Aspirin 100mg",
                        "severity": "moderate",
                        "issue": "Dosing may need adjustment for pediatric patient",
                        "recommendation": "Consult pediatric dosing guidelines",
                        "evidence": "Standard adult dose; pediatric adjustment required"
                    }
                ],
                "recommended_alternatives": [],
                "confidence_score": 0.92,
                "timestamp": "2025-12-24T10:30:00.000Z"
            }
        }
