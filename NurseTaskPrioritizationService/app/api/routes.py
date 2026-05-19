"""API routes for the Nurse Task Prioritization Service."""
import logging
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import TaskPrioritizationRequest, TaskPrioritizationResponse
from app.services.prioritization_service import PrioritizationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["prioritization"])

prioritization_service = PrioritizationService()


@router.post(
    "/prioritize-tasks",
    response_model=TaskPrioritizationResponse,
    status_code=status.HTTP_200_OK,
    summary="Prioritize nursing tasks",
    description="""
    Receives patient monitoring data, pending nursing tasks, medication schedules,
    abnormal findings, and operational context, then returns a prioritized nursing
    task list ordered by urgency and clinical importance.
    """
)
async def prioritize_tasks(request: TaskPrioritizationRequest) -> TaskPrioritizationResponse:
    """
    Prioritize nursing tasks across assigned patients.

    Args:
        request: Task prioritization request with patients and context

    Returns:
        Prioritization response with ranked tasks

    Raises:
        HTTPException: If request validation fails or processing error occurs
    """
    try:
        response = prioritization_service.process_request(request)
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
    """Health check endpoint with OpenAI config and connectivity check."""
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
        "service": "nurse-task-prioritization",
        "provider": "openai",
        "openai_configured": openai_configured,
        "api_accessible": api_accessible,
        "model": settings.openai_model if openai_configured else None,
        "version": settings.api_version
    }
