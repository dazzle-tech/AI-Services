"""Pydantic request and response schemas for Medical Imaging Assist."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ---------- Request models ----------


class ReportCorrectionRequest(BaseModel):
    """Request body for /api/v1/report-correction."""

    doctor_notes: str = Field(..., min_length=1, description="Free-text clinical notes from the ordering physician.")
    radiologist_notes: str = Field(..., min_length=1, description="Free-text read from the radiologist.")
    exam_type: Optional[str] = Field(None, description="Optional exam type, e.g. 'Chest X-ray PA/Lateral'.")
    extracted_dicom_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="DICOM metadata key/value pairs (PatientID, Modality, BodyPartExamined, ViewPosition, ...).",
    )


class AnalysisMatchingRequest(BaseModel):
    """Request body for /api/v1/analysis-matching."""

    clinical_report: str = Field(..., min_length=1, description="Finalized clinical report (authoritative).")
    ai_image_analysis: Dict[str, Any] = Field(
        ..., description="JSON output from the upstream AI image analysis model."
    )
    extracted_dicom_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="DICOM metadata key/value pairs."
    )


# ---------- Response sub-models ----------


class Finding(BaseModel):
    """A single reconciled finding."""

    label: str
    location: Optional[str] = None
    status: Optional[str] = None
    size_cm: Optional[float] = None
    source: Literal["doctor", "radiologist", "clinical_report", "ai", "reconciled"]


class Warning_(BaseModel):
    """A normalization-stage warning surfaced to the radiologist."""

    severity: Literal["info", "high", "critical"]
    code: str
    message: str


class Icd10Match(BaseModel):
    """An ICD-10 code suggestion grounded in the local RAG store."""

    code: str
    term: str
    matched_phrase: str


class RadLexMatch(BaseModel):
    """A RadLex term suggestion grounded in the local RAG store."""

    id: str
    term: str
    matched_phrase: str


class RagGrounding(BaseModel):
    """Container for retrieval-grounded code and term suggestions."""

    icd10_codes: List[Icd10Match] = Field(default_factory=list)
    radlex_terms: List[RadLexMatch] = Field(default_factory=list)


class SafetyNormalizedOutput(BaseModel):
    """Safety-normalized response payload consumed by the radiologist."""

    study_metadata: Dict[str, Any] = Field(default_factory=dict)
    exam_type: str
    findings: List[Finding] = Field(default_factory=list)
    confidence: Literal["High", "Medium", "Low"]
    priority: Literal["Urgent", "Routine"]
    warnings: List[Warning_] = Field(default_factory=list)
    critical_alert: bool = False
    rag_grounding: RagGrounding = Field(default_factory=RagGrounding)

    # Endpoint 1 (report-correction) extra fields
    corrected_doctor_notes: Optional[str] = None
    corrected_radiologist_notes: Optional[str] = None
    structured_report: Optional[Dict[str, Any]] = None
    spelling_corrections: Optional[Dict[str, str]] = None

    # Endpoint 2 (analysis-matching) extra fields
    reconciled_findings: Optional[List[Dict[str, Any]]] = None
    ai_findings_dropped: Optional[List[Dict[str, Any]]] = None
    ai_findings_used_for_enrichment: Optional[List[Dict[str, Any]]] = None


class AssistiveResponse(BaseModel):
    """Top-level response envelope with sibling architecture."""

    raw_model_output: Dict[str, Any]
    safety_normalized_output: SafetyNormalizedOutput
    disclaimer: str
    output_file: Optional[str] = None


# ---------- Health / summary ----------


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
