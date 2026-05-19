"""API routes for the Lab Result Interpreter Service."""
import logging
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import LabInterpretationRequest, LabInterpretationResponse
from app.services.lab_interpreter_service import LabInterpreterService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["lab-interpretation"])

# Initialize service
lab_interpreter_service = LabInterpreterService()


@router.post(
    "/interpret-labs",
    response_model=LabInterpretationResponse,
    status_code=status.HTTP_200_OK,
    summary="Interpret lab results",
    description="""
    Interprets lab results and optional historical labs to produce a structured
    interpretation including abnormal findings, clinically meaningful patterns,
    trends, and suggested follow-up considerations. This is interpretation support
    only—not a diagnosis. Use patient context only when provided.
    """,
)
async def interpret_labs(request: LabInterpretationRequest) -> LabInterpretationResponse:
    """
    Interpret lab results with optional patient context and historical comparison.

    Args:
        request: Lab interpretation request

    Returns:
        Structured interpretation with key_findings, patterns, trends, and follow-up

    Raises:
        HTTPException: If validation or processing fails
    """
    try:
        response = lab_interpreter_service.process_request(request)
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
    """Health check endpoint with OpenAI API status."""
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
        "service": "lab-result-interpreter",
        "provider": "openai",
        "openai_configured": openai_configured,
        "api_accessible": api_accessible,
        "model": settings.openai_model if openai_configured else None,
        "version": settings.api_version
    }
