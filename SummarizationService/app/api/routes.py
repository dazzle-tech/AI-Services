"""API routes for the Clinical Summary Service."""
import logging
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import (
    SummaryRequest,
    SummaryResponse,
    EncounterSummaryRequest,
    EncounterSummaryResponse,
)
from app.services.summarization_service import SummarizationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["summarization"])

# Initialize service
summarization_service = SummarizationService()


@router.post(
    "/summarize",
    response_model=SummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate clinical summary from patient data",
    description="""
    Generates a concise, coherent clinical summary paragraph from structured patient data.
    Uses OpenAI to rephrase patient information into professional clinical documentation
    while preserving all original details, abbreviations, and medical terminology.
    """
)
async def summarize(request: SummaryRequest) -> SummaryResponse:
    """
    Generate a clinical summary from patient data.
    
    Args:
        request: Summary request with patient data
        
    Returns:
        Summary response with generated clinical summary
        
    Raises:
        HTTPException: If request validation fails or processing error occurs
    """
    try:
        response = summarization_service.process_request(request)
        return response
        
    except ValueError as e:
        logger.error(f"Validation error for request {request.request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request validation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error processing request {request.request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post(
    "/encounter-summary",
    response_model=EncounterSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate clinical overview from encounter chart data",
    description="""
    Generates an encounter clinical overview from physician/nurse/hospital-course notes,
    diagnoses, medications, allergies, warnings, order results, and vital signs.
    Supports detail_level and optional extra_prompt instructions.
    """,
)
async def encounter_summary(request: EncounterSummaryRequest) -> EncounterSummaryResponse:
    """Generate a clinical overview summary for one encounter."""
    try:
        return summarization_service.process_encounter_request(request)
    except ValueError as e:
        logger.error("Validation error for encounter %s: %s", request.encounter_id, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request validation failed: {str(e)}",
        )
    except Exception as e:
        logger.error("Unexpected error for encounter %s: %s", request.encounter_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint"
)
async def health_check():
    """Health check endpoint with GPT-4 API status."""
    from app.core.config import settings
    from openai import OpenAI
    
    openai_configured = bool(settings.openai_api_key)
    
    # Test API connectivity if configured
    api_accessible = False
    if openai_configured:
        try:
            # Simple connectivity test - check if API key format is valid
            # (Full connectivity test would require an actual API call)
            api_key = settings.openai_api_key
            api_accessible = api_key.startswith("sk-") and len(api_key) > 20
        except Exception as e:
            logger.warning(f"OpenAI API key validation failed: {e}")
            api_accessible = False
    
    return {
        "status": "healthy" if (openai_configured and api_accessible) else "degraded",
        "service": "clinical-summary",
        "provider": "openai",
        "openai_configured": openai_configured,
        "api_accessible": api_accessible,
        "model": settings.openai_model if openai_configured else None,
        "version": settings.api_version
    }

