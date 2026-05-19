"""API routes for the Patient Timeline Service."""
import logging

from fastapi import APIRouter, HTTPException, status

from app.models.schemas import TimelineRequest, TimelineResponse
from app.services.timeline_service import TimelineService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["patient-timeline"])

# Initialize service
timeline_service = TimelineService()


@router.post(
    "/generate-timeline",
    response_model=TimelineResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate patient timeline from patient data",
    description="""
    Generates a chronological patient timeline from structured and semi-structured
    patient data. Uses OpenAI to identify clinically important events while preserving
    medical terminology, values, and traceability to the original data source.
    """
)
async def generate_timeline(request: TimelineRequest) -> TimelineResponse:
    """
    Generate a patient timeline from patient data.

    Args:
        request: Timeline request with patient data

    Returns:
        Timeline response with clinically important chronological events

    Raises:
        HTTPException: If request validation fails or processing error occurs
    """
    try:
        response = timeline_service.process_request(request)
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


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint"
)
async def health_check():
    """Health check endpoint with OpenAI configuration status."""
    from app.core.config import settings

    openai_configured = bool(settings.openai_api_key)

    api_accessible = False
    if openai_configured:
        try:
            api_key = settings.openai_api_key
            api_accessible = api_key.startswith("sk-") and len(api_key) > 20
        except Exception as e:
            logger.warning(f"OpenAI API key validation failed: {e}")
            api_accessible = False

    return {
        "status": "healthy" if (openai_configured and api_accessible) else "degraded",
        "service": "patient-timeline",
        "provider": "openai",
        "openai_configured": openai_configured,
        "api_accessible": api_accessible,
        "model": settings.openai_model if openai_configured else None,
        "version": settings.api_version
    }
