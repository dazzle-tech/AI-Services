"""
Pydantic models for API request/response validation
"""

from typing import Optional, List, Any, Dict
from pydantic import BaseModel
from enum import Enum


class SeverityLevel(str, Enum):
    """Severity levels for guideline violations."""
    ROUTINE = "routine"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"


class MedicalNote(BaseModel):
    """A single medical note about a guideline deviation or concern."""
    issue: str
    reasoning: str
    affected_orders: List[str]
    severity: SeverityLevel
    recommendations: List[str]
    guideline_reference: Optional[str] = None
    requires_human_review: bool = False


class GuidelineCheckRequest(BaseModel):
    """Full guideline validation request with complete patient data."""
    patient_id: str
    active_orders: Dict[str, List[Dict[str, Any]]]
    clinical_context: Dict[str, Any]
    patient_record: Dict[str, Any]
    specialty: Optional[str] = None


class GuidelineCheckResponse(BaseModel):
    """Response from guideline validation check."""
    patient_id: str
    check_timestamp: str
    overall_severity: SeverityLevel
    summary: str
    medical_notes: List[MedicalNote]
    total_issues_found: int
    critical_count: int
    high_count: int
    moderate_count: int
    routine_count: int
    safety_disclaimer: str
    requires_urgent_review: bool
    guidelines_consulted: List[str]


class QuickGuidelineCheckRequest(BaseModel):
    """Simplified request using patient_id to fetch sample data."""
    patient_id: str
    specialty: Optional[str] = None