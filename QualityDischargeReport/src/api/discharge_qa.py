"""API endpoint for discharge QA."""

import sys
from pathlib import Path

# Add project root to path for imports
if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from src.services.discharge_qa.service import DischargeQAService

router = APIRouter(prefix="/discharge", tags=["discharge"])


class QARequest(BaseModel):
    """Request model for QA endpoint."""
    discharge_report: Any = Field(..., description="Discharge report (text or JSON)")
    patient_record: Dict[str, Any] = Field(..., description="Anonymized patient record")
    onsite_docs: List[Dict[str, Any]] = Field(default_factory=list, description="Onsite clinical documents")
    report_template: Optional[Dict[str, Any]] = Field(None, description="Optional report template")
    quality_rules: Optional[Dict[str, Any]] = Field(None, description="Optional quality rules")


class QAResponse(BaseModel):
    """Response model for QA endpoint."""
    qa_method: str
    overall_score: float
    summary: str
    parsed_report: Dict[str, Any]
    errors: List[Dict[str, Any]]
    missing_items: List[Dict[str, Any]]
    inconsistencies: List[Dict[str, Any]]
    recommended_corrections: List[Dict[str, Any]]


@router.post("/qa/direct", response_model=QAResponse)
async def perform_direct_qa(request: QARequest) -> QAResponse:
    """Perform Direct QA on a discharge report.
    
    Args:
        request: QA request with discharge report and supporting documents
        
    Returns:
        QA results with errors, inconsistencies, and recommendations
    """
    try:
        service = DischargeQAService()
        
        result = service.perform_qa(
            discharge_report=request.discharge_report,
            patient_record=request.patient_record,
            onsite_docs=request.onsite_docs,
            report_template=request.report_template,
            quality_rules=request.quality_rules
        )
        
        return QAResponse(**result)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QA analysis failed: {str(e)}")

