from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime


class Patient(BaseModel):
    """Patient information model"""
    mrn: str = Field(..., description="Medical Record Number")
    fullName: str = Field(..., description="Patient full name")
    gender: str = Field(..., description="Patient gender")
    dob: str = Field(..., description="Date of birth (YYYY-MM-DD)")
    
    @validator('gender')
    def validate_gender(cls, v):
        allowed = ['Male', 'Female', 'Other', 'Unknown']
        if v not in allowed:
            raise ValueError(f"Gender must be one of {allowed}")
        return v


class Encounter(BaseModel):
    """Encounter/visit information model"""
    visitId: str = Field(..., description="Visit identifier")
    visitType: str = Field(..., description="Type of visit")
    plannedStartDate: str = Field(..., description="Planned start date")
    chiefComplaint: str = Field(..., description="Chief complaint")
    patientAge: str = Field(..., description="Patient age (formatted)")
    diagnosis: str = Field(..., description="Primary diagnosis with ICD code")


class Diagnosis(BaseModel):
    """Diagnosis information model"""
    type: str = Field(..., description="Type of diagnosis")
    value: str = Field(..., description="Diagnosis code and description")


class MedicationValidationRequest(BaseModel):
    """Request model for medication validation"""
    patient: Patient
    encounter: Encounter
    complain: str = Field(..., description="Chief complaint")
    diagnosis: Diagnosis
    medications: List[str] = Field(..., description="List of medications to validate")
    
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
                    "diagnosis": "I20.0,Unstable angina"
                },
                "complain": "Chest pain",
                "diagnosis": {
                    "type": "Encounter Diagnosis",
                    "value": "I20.0,Unstable angina"
                },
                "medications": [
                    "Medication Name: Aspirin | Active Ingredients: Acetylsalicylic acid - 100 mg"
                ]
            }
        }


class TestValidationRequest(BaseModel):
    """Request model for test validation"""
    patient: Patient
    encounter: Encounter
    complain: str = Field(..., description="Chief complaint")
    diagnosis: Diagnosis
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
                    "diagnosis": "I20.0,Unstable angina"
                },
                "complain": "Chest pain",
                "diagnosis": {
                    "type": "Encounter Diagnosis",
                    "value": "I20.0,Unstable angina"
                },
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