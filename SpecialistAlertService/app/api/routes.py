"""API routes for the Specialist Alert Service."""
import logging

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.models.schemas import AlertRequest, AlertResponse
from app.services.alert_service import SpecialistAlertService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["specialist-alerts"])

alert_service = SpecialistAlertService()


@router.post(
    "/generate-alerts",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate clinical alerts and specialist consultation recommendations",
    description="""
    Reviews a full patient record and returns clinically grounded alerts for
    escalation needs, specialist consultation triggers, medication safety concerns,
    abnormal patterns, care gaps, and follow-up issues.
    """,
)
async def generate_alerts(request: AlertRequest) -> AlertResponse:
    """
    Generate structured clinical alerts from a patient record.

    Args:
        request: Alert request with patient record

    Returns:
        Alert response with structured alerts and processing metadata

    Raises:
        HTTPException: If request validation fails or processing error occurs
    """
    try:
        response = alert_service.process_request(request)
        return response

    except ValueError as e:
        logger.error("Validation error for request %s: %s", request.request_id, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request validation failed: {str(e)}",
        )
    except Exception as e:
        logger.error("Unexpected error processing request %s: %s", request.request_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
)
async def health_check():
    """Health check endpoint with OpenAI configuration status."""
    openai_configured = bool(settings.openai_api_key)

    api_accessible = False
    if openai_configured:
        try:
            api_key = settings.openai_api_key
            api_accessible = api_key.startswith("sk-") and len(api_key) > 20
        except Exception as e:
            logger.warning("OpenAI API key validation failed: %s", e)
            api_accessible = False

    return {
        "status": "healthy" if (openai_configured and api_accessible) else "degraded",
        "service": "specialist-alert",
        "provider": "openai",
        "openai_configured": openai_configured,
        "api_accessible": api_accessible,
        "model": settings.openai_model if openai_configured else None,
        "version": settings.api_version,
    }
