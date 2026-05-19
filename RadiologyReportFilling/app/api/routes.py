"""API routes for Medical Imaging Assist."""
import logging

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.models.schemas import (
    AnalysisMatchingRequest,
    AssistiveResponse,
    HealthResponse,
    ReportCorrectionRequest,
    TermsSummaryResponse,
)
from app.services.medical_service import MedicalImagingService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["medical-imaging"])

_service: MedicalImagingService | None = None


def _get_service() -> MedicalImagingService:
    """Return the singleton service, instantiating on first call."""
    global _service
    if _service is None:
        _service = MedicalImagingService()
    return _service


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health() -> HealthResponse:
    """Report basic configuration and load status."""
    try:
        service = _get_service()
        status = "healthy" if settings.openai_api_key else "degraded"
    except Exception as exc:
        logger.warning("Health check degraded: %s", exc)
        return HealthResponse(
            status="degraded",
            service="medical-imaging-assist",
            version=settings.api_version,
            model=settings.openai_model,
            openai_configured=bool(settings.openai_api_key),
            icd10_file=settings.icd10_file,
            radlex_file=settings.radlex_file,
        )
    _ = service
    return HealthResponse(
        status=status,
        service="medical-imaging-assist",
        version=settings.api_version,
        model=settings.openai_model,
        openai_configured=bool(settings.openai_api_key),
        icd10_file=settings.icd10_file,
        radlex_file=settings.radlex_file,
    )


@router.get(
    "/terms/summary",
    response_model=TermsSummaryResponse,
    summary="Quick counts from the loaded RAG term files (no AI call)",
)
async def terms_summary() -> TermsSummaryResponse:
    """Return counts of loaded ICD-10 and RadLex entries."""
    try:
        service = _get_service()
        stats = service.get_terms_summary()
        return TermsSummaryResponse(**stats)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")


@router.post(
    "/report-correction",
    response_model=AssistiveResponse,
    summary="Correct radiology report and ground in ICD-10/RadLex",
    description=(
        "Cross-checks doctor and radiologist notes, fixes spelling, expands shorthand, "
        "and grounds findings in ICD-10/RadLex via the local RAG store. Flags laterality "
        "conflicts and anatomy/metadata mismatches."
    ),
)
async def report_correction(payload: ReportCorrectionRequest) -> AssistiveResponse:
    """Run report-correction pipeline."""
    try:
        service = _get_service()
        return service.report_correction(
            doctor_notes=payload.doctor_notes,
            radiologist_notes=payload.radiologist_notes,
            exam_type=payload.exam_type,
            dicom_metadata=payload.extracted_dicom_metadata,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("Unhandled error in report_correction")
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")


@router.post(
    "/analysis-matching",
    response_model=AssistiveResponse,
    summary="Reconcile clinical report with AI image analysis",
    description=(
        "Applies Hierarchy of Truth: the clinical report is authoritative. AI findings "
        "that contradict the report are dropped (with warnings); AI findings that add "
        "non-conflicting detail are used to enrich the final report."
    ),
)
async def analysis_matching(payload: AnalysisMatchingRequest) -> AssistiveResponse:
    """Run analysis-matching pipeline."""
    try:
        service = _get_service()
        return service.analysis_matching(
            clinical_report=payload.clinical_report,
            ai_image_analysis=payload.ai_image_analysis,
            dicom_metadata=payload.extracted_dicom_metadata,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("Unhandled error in analysis_matching")
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")
