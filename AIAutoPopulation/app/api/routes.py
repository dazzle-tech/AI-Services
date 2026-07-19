"""API routes for the AI Auto-Population Service."""
import logging
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import AutoPopulationRequest, AutoPopulationResponse
from app.models.schemas_v2 import AutoPopulationRequestV2, AutoPopulationResponseV2
from app.services.auto_population_service import AutoPopulationService
from app.services.auto_population_service_v2 import AutoPopulationServiceV2

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["auto-population"])

# Initialize services
auto_population_service = AutoPopulationService()
auto_population_service_v2 = AutoPopulationServiceV2()


@router.post(
    "/auto-populate",
    response_model=AutoPopulationResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract structured medical data from free text",
    description="""
    Extracts structured medical data from clinician free-text input.
    Cross-checks extracted data against onsite patient records.
    Returns safe, auditable JSON output.
    """
)
async def auto_populate(request: AutoPopulationRequest) -> AutoPopulationResponse:
    """
    Process auto-population request.
    
    Args:
        request: Auto-population request with user text and patient data
        
    Returns:
        Auto-population response with structured data
        
    Raises:
        HTTPException: If request validation fails or processing error occurs
    """
    try:
        # Validate request (Pydantic handles basic validation)
        # Additional business logic validation happens in service layer
        
        # Process request
        response = auto_population_service.process_request(request)
        
        # Check for critical errors
        critical_errors = [w for w in response.warnings if w.level == "error"]
        if critical_errors:
            logger.warning(
                f"Request {request.request_id} completed with errors: "
                f"{[e.message for e in critical_errors]}"
            )
        
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
    "/auto-populate/v2",
    response_model=AutoPopulationResponseV2,
    status_code=status.HTTP_200_OK,
    response_model_exclude_none=True,  # Exclude None fields from response
    summary="Extract structured medical data from free text (V2 API)",
    description="""
    V2 API with clean contract:
    - Organized request structure (user, languages, inputs, requested_outputs)
    - Organized response structure (outputs, quality, trace, metadata)
    - Support for summary generation
    - Improved field path notation
    - Optional quality and trace sections
    """
)
async def auto_populate_v2(request: AutoPopulationRequestV2) -> AutoPopulationResponseV2:
    """
    Process auto-population request (V2 format).
    
    Args:
        request: Auto-population request in V2 format
        
    Returns:
        Auto-population response in V2 format
        
    Raises:
        HTTPException: If request validation fails or processing error occurs
    """
    try:
        response = auto_population_service_v2.process_request(request)
        
        # Check for critical errors (if quality section is present)
        if response.quality and response.quality.warnings:
            critical_errors = [w for w in response.quality.warnings if w.level == "error"]
            if critical_errors:
                logger.warning(
                    f"Request {request.request_id} completed with errors: "
                    f"{[e.message for e in critical_errors]}"
                )
        
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
    """Health check endpoint."""
    return {"status": "healthy", "service": "ai-auto-population"}

