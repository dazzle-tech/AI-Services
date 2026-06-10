from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ExamType(str, Enum):
    CT_CHEST_ABDOMEN_PELVIS = "CT_CHEST_ABDOMEN_PELVIS"
    CT_ABDOMEN = "CT_ABDOMEN"
    CT_ABDOMEN_PELVIS = "CT_ABDOMEN_PELVIS"
    CT_CHEST = "CT_CHEST"
    CT_HEAD = "CT_HEAD"
    XRAY = "XRAY"
    XRAY_UNKNOWN = "XRAY_UNKNOWN"
    XR_CHEST = "XR_CHEST"
    XR_CHEST_PA = "XR_CHEST_PA"
    XR_CHEST_AP = "XR_CHEST_AP"
    XR_CHEST_LATERAL = "XR_CHEST_LATERAL"
    MRI_LUMBAR_SPINE = "MRI_LUMBAR_SPINE"
    UNKNOWN = "UNKNOWN"


class QCStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class IssueType(str, Enum):
    INCOMPLETE_ANATOMICAL_COVERAGE = "INCOMPLETE_ANATOMICAL_COVERAGE"
    NO_ISSUE = "NO_ISSUE"
    UNSUPPORTED_PROTOCOL = "UNSUPPORTED_PROTOCOL"
    PIPELINE_ERROR = "PIPELINE_ERROR"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    MISSING_VIEW = "MISSING_VIEW"
    MISSING_METADATA = "MISSING_METADATA"
    WRONG_BODY_PART = "WRONG_BODY_PART"
    NO_IMAGES = "NO_IMAGES"
    POOR_EXPOSURE = "POOR_EXPOSURE"


class MissingRegion(str, Enum):
    SUPERIOR_CHEST = "SUPERIOR_CHEST"
    INFERIOR_CHEST = "INFERIOR_CHEST"
    SUPERIOR_HEAD = "SUPERIOR_HEAD"
    INFERIOR_HEAD = "INFERIOR_HEAD"
    SUPERIOR_ABDOMEN = "SUPERIOR_ABDOMEN"
    MID_ABDOMEN = "MID_ABDOMEN"
    LOWER_PELVIS = "LOWER_PELVIS"
    LATERAL_VIEW = "LATERAL_VIEW"
    UNKNOWN = "UNKNOWN"


class RequiredLandmark(str, Enum):
    LUNG_APICES = "LUNG_APICES"
    LUNG_BASES = "LUNG_BASES"
    SKULL_VERTEX = "SKULL_VERTEX"
    SKULL_BASE = "SKULL_BASE"
    DIAPHRAGM_OR_LUNG_BASES = "DIAPHRAGM_OR_LUNG_BASES"
    LIVER_DOME = "LIVER_DOME"
    PUBIC_SYMPHYSIS = "PUBIC_SYMPHYSIS"
    BLADDER = "BLADDER"
    KIDNEYS = "KIDNEYS"
    UNKNOWN = "UNKNOWN"


class QCResult(BaseModel):
    study_instance_uid: str
    exam_type: ExamType
    qc_status: QCStatus
    issue_type: IssueType
    missing_region: Optional[MissingRegion] = None
    required_landmark_not_seen: Optional[RequiredLandmark] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    recommended_action: str
    human_review_required: bool = True
    explanation: str
    disclaimer: str

    # Optional structured details for debugging/integration (never PHI)
    details: Dict[str, Any] = Field(default_factory=dict)


class ExplainRequest(BaseModel):
    qc_result: Dict[str, Any]
    style: str = Field(default="technologist_alert")
    OutputLanguage: str = Field(
        default="el",
        description="Language code for generated explanation text. Examples: el, en, ar."
    )


class ExplainResponse(BaseModel):
    explanation: str
