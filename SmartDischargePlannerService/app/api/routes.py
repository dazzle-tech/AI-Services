"""API routes for the Smart Discharge Planner Service."""
import logging
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import DischargePlanningRequest, DischargePlanningResponse
from app.services.discharge_planner_service import DischargePlannerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["discharge-planning"])

discharge_planner_service = DischargePlannerService()


@router.post(
    "/plan-discharge",
    response_model=DischargePlanningResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate discharge planning assessment",
    description="""
    Receives discharge-related clinical and operational patient data, then returns
    a structured discharge readiness assessment, blockers, follow-up considerations,
    medication reconciliation concerns, and a draft discharge planning summary.
    Supports discharge planning only—does not make the final discharge decision.
    """
)
async def plan_discharge(request: DischargePlanningRequest) -> DischargePlanningResponse:
    """
    Generate discharge planning assessment from patient data.
    
    Args:
        request: Discharge planning request with patient context and data
        
    Returns:
        Discharge planning response with assessment and blockers
        
    Raises:
        HTTPException: If request validation fails or processing error occurs
    """
    try:
        response = discharge_planner_service.process_request(request)
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
    """Health check endpoint with OpenAI config status."""
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
        "service": "smart-discharge-planner",
        "provider": "openai",
        "openai_configured": openai_configured,
        "api_accessible": api_accessible,
        "model": settings.openai_model if openai_configured else None,
        "version": settings.api_version
    }
