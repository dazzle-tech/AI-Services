"""API routes for the Role-Aware Timeline Service."""
import logging

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.models.schemas import RoleTimelineRequest, RoleTimelineResponse
from app.services.timeline_service import TimelineService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["role-aware-timeline"])
timeline_service = TimelineService()


@router.post(
    "/generate-role-timeline",
    response_model=RoleTimelineResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a shared timeline, a shared summary, and highlights for one role",
    description=(
        "Reads a chart extract and viewer_role. Builds the timeline, writes one "
        "problem-oriented summary from those events, then writes highlights for "
        "nurse, radiologist, or cardiologist. The summary does not change with the role."
    ),
)
async def generate_role_timeline(request: RoleTimelineRequest) -> RoleTimelineResponse:
    """Generate the three layers for one chart and one role."""
    try:
        return timeline_service.process_request(request)
    except ValueError as exc:
        logger.error("Role timeline request failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request validation failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.error("Unexpected role timeline error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {exc}",
        ) from exc


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check",
)
async def health_check():
    """Report whether OpenAI settings are present. This does not call the model."""
    configured = bool(settings.openai_api_key and settings.openai_model)
    return {
        "status": "healthy" if configured else "degraded",
        "service": "role-aware-timeline",
        "provider": "openai",
        "openai_configured": configured,
        "model": settings.openai_model if configured else None,
        "version": settings.api_version,
    }
