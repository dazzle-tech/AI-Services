from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from typing import Dict, Any
import logging

from models.schemas import (
    MedicationValidationRequest,
    TestValidationRequest,
    ValidationResponse
)
from services.medication_tests_validation_service import (
    MedicationValidationService,
    TestValidationService
)
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Clinical Validation API",
    description="AI-powered medication and test validation system",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
medication_service = MedicationValidationService()
test_service = TestValidationService()


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Clinical Validation API",
        "version": "1.0.0",
        "status": "active",
        "endpoints": {
            "medication_validation": "/api/v1/validate/medication",
            "test_validation": "/api/v1/validate/tests",
            "health": "/health"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "services": {
            "medication_validation": "operational",
            "test_validation": "operational"
        }
    }


@app.post(
    "/api/v1/validate/medication",
    response_model=ValidationResponse,
    status_code=status.HTTP_200_OK
)
async def validate_medication(request: MedicationValidationRequest) -> ValidationResponse:
    """
    Validate medications against patient data for potential conflicts.
    
    Args:
        request: Medication validation request containing patient and medication data
        
    Returns:
        ValidationResponse with safety assessment and recommendations
    """
    try:
        logger.info(f"Processing medication validation for patient MRN: {request.patient.mrn}")
        
        result = await medication_service.validate(request)
        
        logger.info(
            f"Medication validation completed - Status: {result.quick_summary.overall_status}"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error in medication validation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Medication validation failed: {str(e)}"
        )


@app.post(
    "/api/v1/validate/tests",
    response_model=ValidationResponse,
    status_code=status.HTTP_200_OK
)
async def validate_tests(request: TestValidationRequest) -> ValidationResponse:
    """
    Validate diagnostic tests against patient data for potential conflicts.
    
    Args:
        request: Test validation request containing patient and test data
        
    Returns:
        ValidationResponse with safety assessment and recommendations
    """
    try:
        logger.info(f"Processing test validation for patient MRN: {request.patient.mrn}")
        
        result = await test_service.validate(request)
        
        logger.info(
            f"Test validation completed - Status: {result.quick_summary.overall_status}"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error in test validation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test validation failed: {str(e)}"
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.detail,
                "status_code": exc.status_code
            }
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "message": "An internal error occurred",
                "status_code": 500
            }
        }
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )