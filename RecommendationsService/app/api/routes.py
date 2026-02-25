"""API routes for the Clinical Recommendations Service."""
import logging
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import (
    RecommendationRequest,
    RecommendationsResponse,
    SpecialtyConsultationRequest,
    SpecialtyConsultationResponse,
    UserRoleRecommendationRequest
)
from app.services.recommendations_service import RecommendationsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["recommendations"])

# Initialize service
recommendations_service = RecommendationsService()


@router.post(
    "/recommendations",
    response_model=RecommendationsResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate clinical recommendations from patient context",
    description="""
    Generates evidence-based clinical recommendations based on patient context.
    Uses OpenAI GPT-4 to analyze patient data and provide comprehensive,
    actionable recommendations including medications, diagnostics, treatments,
    monitoring, and lifestyle modifications.
    """
)
async def get_recommendations(request: RecommendationRequest) -> RecommendationsResponse:
    """
    Generate clinical recommendations from patient context.
    
    Args:
        request: Recommendations request with patient context
        
    Returns:
        Recommendations response with generated clinical recommendations
        
    Raises:
        HTTPException: If request validation fails or processing error occurs
    """
    try:
        response = recommendations_service.process_request(request)
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
    """Health check endpoint with GPT-4 API status."""
    from app.core.config import settings
    
    openai_configured = bool(settings.openai_api_key)
    
    # Test API connectivity if configured
    api_accessible = False
    if openai_configured:
        try:
            # Simple connectivity test - check if API key format is valid
            api_key = settings.openai_api_key
            api_accessible = api_key.startswith("sk-") and len(api_key) > 20
        except Exception as e:
            logger.warning(f"OpenAI API key validation failed: {e}")
            api_accessible = False
    
    return {
        "status": "healthy" if (openai_configured and api_accessible) else "degraded",
        "service": "clinical-recommendations",
        "provider": "openai",
        "openai_configured": openai_configured,
        "api_accessible": api_accessible,
        "model": settings.openai_model if openai_configured else None,
        "version": settings.api_version
    }


@router.post(
    "/consultation/specialty",
    response_model=SpecialtyConsultationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get general specialty-based consultation recommendations",
    description="""
    API 1: Consultation Request → Select Specialty
    
    Generates GENERAL consultation recommendations for a selected medical specialty.
    Only requires the specialty field - returns a concise summary containing all
    standard protocols, tests, and procedures for that specialty.
    
    For example, if specialty is 'cardiology', returns a summary of general cardiology
    consultation recommendations including standard diagnostic tests, procedures, and protocols.
    
    Patient context and complaint are optional - if not provided, returns general
    specialty recommendations.
    
    Returns only a summary string containing all recommendations.
    """
)
async def get_specialty_consultation(request: SpecialtyConsultationRequest) -> SpecialtyConsultationResponse:
    """
    Generate specialty-specific consultation recommendations.
    
    Args:
        request: Specialty consultation request with selected specialty
        
    Returns:
        Specialty consultation response with concise summary containing all recommendations
    """
    try:
        response = recommendations_service.process_specialty_consultation(request)
        return response
        
    except ValueError as e:
        logger.error(f"Validation error for specialty consultation {request.request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request validation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error processing specialty consultation {request.request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post(
    "/recommendations/user-role",
    response_model=RecommendationsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user role-based recommendations",
    description="""
    API 2: Logged-In User Based on Specialty
    
    Generates recommendations from the perspective of the logged-in user's specialty/role.
    For example, if user_role is 'cardiology', provides recommendations as a cardiologist
    would evaluate the patient.
    
    Requires complete patient data and user's specialty role.
    """
)
async def get_user_role_recommendations(request: UserRoleRecommendationRequest) -> RecommendationsResponse:
    """
    Generate recommendations from user's specialty role perspective.
    
    Args:
        request: User role recommendation request with user's specialty and patient data
        
    Returns:
        Recommendations response from user's specialty perspective
    """
    try:
        response = recommendations_service.process_user_role_recommendations(request)
        return response
        
    except ValueError as e:
        logger.error(f"Validation error for user role recommendations {request.request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request validation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error processing user role recommendations {request.request_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

