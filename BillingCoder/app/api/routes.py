"""API routes for CodingAssist REST endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.models.schemas import (
    CodingEditsSummaryResponse,
    GenerateChargeRequest,
    GenerateChargeResponse,
    HealthResponse,
)
from app.rag.store import get_rag_store
from app.services.coding_service import CodingService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["coding"])

_service: Optional[CodingService] = None


def _get_service() -> CodingService:
    """Return the singleton service, creating it on first call."""
    global _service
    if _service is None:
        _service = CodingService()
    return _service


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Reports service status, model configuration, and RAG readiness.",
)
async def health():
    """Return a snapshot of service readiness."""
    try:
        service = _get_service()
        summary = service.coding_edits_summary()
        rag_count = get_rag_store().count()
        return HealthResponse(
            status="healthy" if rag_count > 0 else "degraded",
            service="CodingAssist",
            version=settings.api_version,
            model=settings.openai_model,
            openai_configured=bool(settings.openai_api_key),
            rag_initialized=rag_count > 0,
            rag_term_count=rag_count,
            ptp_edit_count=summary["ptp_edit_count"],
            mue_rule_count=summary["mue_rule_count"],
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")


@router.get(
    "/coding-edits/summary",
    response_model=CodingEditsSummaryResponse,
    summary="Summarize deterministic edit rules",
    description="Returns counts and contents of the loaded NCCI PTP edits and MUE limits. No AI call.",
)
async def coding_edits_summary():
    """Return the configured edit-rules summary."""
    try:
        service = _get_service()
        summary = service.coding_edits_summary()
        return CodingEditsSummaryResponse(**summary)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")


@router.post(
    "/charges/generate",
    response_model=GenerateChargeResponse,
    summary="Generate a structured charge ticket",
    description=(
        "Runs the full 6-phase pipeline: normalize (reconcile multi-document "
        "input), extract+ground (RAG + live NLM Clinical Tables ICD-10-CM/"
        "HCPCS), deterministic NCCI/MUE/medical-necessity compliance check, "
        "generative charge-ticket drafting, and deterministic enforcement of "
        "blocking compliance flags before persisting and returning the result."
    ),
)
async def generate_charge(payload: GenerateChargeRequest):
    """Execute the full charge-capture pipeline."""
    try:
        service = _get_service()
        upstream = payload.upstream_entities
        result = service.generate_charge(
            encounter_metadata=payload.encounter_metadata.model_dump(),
            documents=[d.model_dump() for d in payload.documents],
            upstream_entities=[u.model_dump() for u in upstream] if upstream else None,
        )
        return GenerateChargeResponse(**result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}")
