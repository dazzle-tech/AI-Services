"""Internal state models for alert orchestration."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.schemas import Alert


class RiskSignal(BaseModel):
    """Deterministic risk signal extracted from the patient record."""

    signal_type: str = Field(..., description="Type of deterministic signal")
    category: str = Field(..., description="Associated alert category")
    severity: str = Field(..., description="Signal severity")
    summary: str = Field(..., description="Short signal summary")
    evidence: List[str] = Field(default_factory=list, description="Traceable evidence lines")
    recommended_specialty: Optional[str] = Field(
        default=None,
        description="Suggested specialty to consider when relevant",
    )


class OrchestrationState(BaseModel):
    """State container for the controlled alert workflow."""

    request_id: str
    patient_record: Dict[str, Any]
    extracted_signals: List[RiskSignal] = Field(default_factory=list)
    candidate_alerts: List[Alert] = Field(default_factory=list)
    validated_alerts: List[Alert] = Field(default_factory=list)
    final_alerts: List[Alert] = Field(default_factory=list)
    dropped_alert_count: int = 0
