"""Pydantic request and response schemas for the radiology report filling API."""
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SUPPORTED_OUTPUT_LANGUAGES = {"el", "pt", "en", "ar"}


class AIInterpretationSummaryModel(BaseModel):
    """Compact AI interpretation context for report generation."""

    model_config = ConfigDict(extra="ignore")

    status: Optional[str] = None
    critical_alert: bool = False
    summary: Optional[str] = None
    findings_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class QCSummaryModel(BaseModel):
    """Compact QC context for report generation."""

    model_config = ConfigDict(extra="ignore")

    qc_status: Optional[str] = None
    issue_type: Optional[str] = None
    recommended_action: Optional[str] = None
    human_review_required: Optional[bool] = None
    confidence: Optional[float] = None


class RadiologyReportRequest(BaseModel):
    """Public request body for the report filling endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "PatientID": "LIDC-IDRI-0001",
                    "PatientName": "",
                    "OrderID": "",
                    "OrderDate": "2000-01-01T00:00:00",
                    "DateOfBirth": None,
                    "NationalID": "",
                    "Gender": "",
                    "AccessionNumber": "ACC-10008",
                    "OutputLanguage": "el",
                    "AIInterpretationSummary": {
                        "status": "REVIEW_REQUIRED",
                        "critical_alert": False,
                        "summary": "Radiologist review is required.",
                        "findings_count": 0,
                        "warnings": ["Vision model request timed out after 30s."],
                    },
                    "QC": {
                        "qc_status": "REVIEW_REQUIRED",
                        "issue_type": "MISSING_METADATA",
                        "recommended_action": "Verify missing ViewPosition metadata.",
                        "human_review_required": True,
                        "confidence": 0.6,
                    },
                    "DICOM": {
                        "Modality": "US",
                        "BodyPartExamined": "ABDOMEN",
                        "StudyDate": "20260604",
                        "ViewPosition": None,
                        "StudyInstanceUID": "1.2.3.4.5",
                        "DICOMAccessionNumber": "ACC-10008",
                    },
                }
            ]
        }
    )

    PatientID: Optional[str] = None
    PatientName: Optional[str] = None
    OrderID: Optional[str] = None
    OrderDate: Optional[datetime] = None
    DateOfBirth: Optional[datetime] = None
    NationalID: Optional[str] = None
    Gender: Optional[str] = None
    AccessionNumber: str = Field(..., min_length=1)
    OutputLanguage: Optional[str] = Field(
        "el",
        description="Language code for the generated report text. Examples: el, pt, en, ar.",
    )
    ExamType: Optional[str] = None
    DoctorNotes: Optional[str] = None
    RadiologistNotes: Optional[str] = None
    SigningPhysician: Optional[str] = None
    SigningPhysicianCode: Optional[str] = None
    AIInterpretationSummary: Optional[AIInterpretationSummaryModel] = None
    QC: Optional[QCSummaryModel] = None
    DICOM: Optional[Dict[str, Any]] = None

    # Legacy debug/workflow payloads retained for compatibility.
    AIInterpretation: Optional[Dict[str, Any]] = None
    QCResult: Optional[Dict[str, Any]] = None

    @field_validator("OutputLanguage", mode="before")
    @classmethod
    def validate_output_language(cls, value: Optional[str]) -> str:
        """Normalize the requested report language or reject unsupported values."""
        if value in (None, ""):
            return "el"
        normalized = str(value).strip().lower()
        if normalized not in _SUPPORTED_OUTPUT_LANGUAGES:
            supported = ", ".join(sorted(_SUPPORTED_OUTPUT_LANGUAGES))
            raise ValueError(f"OutputLanguage must be one of: {supported}")
        return normalized


class RadiologyTemplateResponse(BaseModel):
    """Public response body for the report filling endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ID": 0,
                "TEMPLATE_NAME": "Radiology Report Template",
                "TEMPLATE_TEXT": "Radiology report template text.",
                "STATUS_ID": None,
                "CREATED_BY": None,
                "CREATION_DATETIME": None,
                "DELETED_BY": None,
                "DELETE_DATETIME": None,
                "UPDATED_BY": None,
                "UPDATE_DATETIME": None,
                "Physician": None,
            }
        }
    )

    ID: int
    TEMPLATE_NAME: str
    TEMPLATE_TEXT: str
    STATUS_ID: Optional[int] = None
    CREATED_BY: Optional[str] = None
    CREATION_DATETIME: Optional[datetime] = None
    DELETED_BY: Optional[str] = None
    DELETE_DATETIME: Optional[datetime] = None
    UPDATED_BY: Optional[str] = None
    UPDATE_DATETIME: Optional[datetime] = None
    Physician: Optional[str] = None


class HealthResponse(BaseModel):
    """Standard health-check response."""

    status: Literal["healthy", "degraded"]
    service: str
    version: str
    model: Optional[str] = None
    openai_configured: bool
    icd10_file: str
    radlex_file: str


class TermsSummaryResponse(BaseModel):
    """Quick counts from the loaded RAG term files (no AI call)."""

    icd10_count: int
    radlex_count: int
    embeddings_present: bool


class WorkflowWarning(BaseModel):
    """Deterministic workflow warning for restored compatibility endpoints."""

    code: str
    message: str
    severity: Literal["low", "medium", "high"] = "medium"


class ReportCorrectionRequest(BaseModel):
    """Workflow request body for report correction."""

    doctor_notes: str = ""
    radiologist_notes: str = ""
    exam_type: str = ""
    extracted_dicom_metadata: Dict[str, Any] = Field(default_factory=dict)


class Icd10Suggestion(BaseModel):
    """Suggested ICD-10 code from local RAG lookup."""

    code: str
    term: str
    matched_phrase: Optional[str] = None


class ReportCorrectionSafetyOutput(BaseModel):
    """Workflow-friendly normalized output for report correction."""

    clinical_report: str
    corrected_radiologist_notes: str
    corrected_doctor_notes: str
    warnings: list[WorkflowWarning] = Field(default_factory=list)
    rag_grounding: Dict[str, Any] = Field(default_factory=dict)


class ReportCorrectionResponse(BaseModel):
    """Compatibility response for the legacy report-correction route."""

    clinical_report_text: str
    confirmed: bool
    warnings: list[WorkflowWarning] = Field(default_factory=list)
    safety_normalized_output: ReportCorrectionSafetyOutput


class AnalysisMatchingRequest(BaseModel):
    """Workflow request body for AI-vs-report reconciliation."""

    clinical_report: str = ""
    ai_image_analysis: Dict[str, Any] = Field(default_factory=dict)
    extracted_dicom_metadata: Dict[str, Any] = Field(default_factory=dict)


class ReconciledFinding(BaseModel):
    """Single reconciled AI finding compared against the clinical report."""

    finding_label: str
    finding_text: str
    location: Optional[str] = None
    match_status: Literal["matched", "partial", "unmatched"]
    in_clinical_report: bool
    confidence: Optional[float] = None
    rationale: str


class AnalysisMatchingSafetyOutput(BaseModel):
    """Workflow-friendly normalized output for analysis matching."""

    reconciled_findings: list[ReconciledFinding] = Field(default_factory=list)
    suggested_icd10_codes: list[Icd10Suggestion] = Field(default_factory=list)
    warnings: list[WorkflowWarning] = Field(default_factory=list)


class AnalysisMatchingResponse(BaseModel):
    """Compatibility response for the legacy analysis-matching route."""

    reconciled_findings: list[ReconciledFinding] = Field(default_factory=list)
    suggested_icd10_codes: list[Icd10Suggestion] = Field(default_factory=list)
    warnings: list[WorkflowWarning] = Field(default_factory=list)
    safety_normalized_output: AnalysisMatchingSafetyOutput
