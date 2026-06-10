"""API routes for the radiology report filling service."""
import logging

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.models.schemas import (
    AnalysisMatchingRequest,
    AnalysisMatchingResponse,
    HealthResponse,
    RadiologyReportRequest,
    RadiologyTemplateResponse,
    ReportCorrectionRequest,
    ReportCorrectionResponse,
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
    response_model=ReportCorrectionResponse,
    summary="Validate radiologist notes against doctor notes and return workflow-safe clinical report text",
)
async def report_correction(payload: ReportCorrectionRequest) -> ReportCorrectionResponse:
    """Restore the legacy workflow contract for report correction."""
    try:
        service = _get_service()
        return service.correct_report(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Unhandled error in report_correction")
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")


@router.post(
    "/analysis-matching",
    response_model=AnalysisMatchingResponse,
    summary="Reconcile AI image findings against the clinical report and suggest ICD-10 codes",
)
async def analysis_matching(payload: AnalysisMatchingRequest) -> AnalysisMatchingResponse:
    """Restore the legacy workflow contract for report-vs-AI reconciliation."""
    try:
        service = _get_service()
        return service.match_analysis(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Unhandled error in analysis_matching")
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")


@router.post(
    "/report-filling",
    response_model=RadiologyTemplateResponse,
    summary="Generate a radiology report template from patient, order, and optional DICOM metadata",
)
async def report_filling(payload: RadiologyReportRequest) -> RadiologyTemplateResponse:
    """Generate the radiology report template response."""
    try:
        service = _get_service()
        return service.generate_report_template(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Unhandled error in report_filling")
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")
