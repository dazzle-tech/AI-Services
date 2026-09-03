from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
import uvicorn
from typing import Dict, Any
import logging

from models.schemas import (
    MedicationValidationRequest,
    TestValidationRequest,
    AllergyDrugValidationRequest,
    ValidationResponse
)
from services.medication_tests_validation_service import (
    MedicationValidationService,
    TestValidationService,
    AllergyDrugValidationService
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

# Initialize services
medication_service = MedicationValidationService()
test_service = TestValidationService()
allergy_drug_service = AllergyDrugValidationService()
logger.info(
    "LLM configured model=%s base_url=%s",
    settings.OPENAI_MODEL,
    settings.OPENAI_BASE_URL,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    client = request.client.host if request.client else "unknown"
    logger.info("Request %s %s from %s", request.method, request.url.path, client)
    response = await call_next(request)
    logger.info("Response %s %s -> %s", request.method, request.url.path, response.status_code)
    return response


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Clinical Validation API",
        "version": "1.0.0",
        "status": "active",
        "auth": "none — no request headers required",
        "endpoints": {
            "medication_validation": "/api/v1/validate/medication",
            "test_validation": "/api/v1/validate/tests",
            "allergy_drug_validation": "/api/v1/validate/allergy-drugs",
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
            "test_validation": "operational",
            "allergy_drug_validation": "operational"
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


@app.post(
    "/api/v1/validate/allergy-drugs",
    response_model=ValidationResponse,
    status_code=status.HTTP_200_OK
)
async def validate_allergy_drugs(request: AllergyDrugValidationRequest) -> ValidationResponse:
    """
    Check proposed drugs against documented allergies.

    Patient demographics are optional. At least one drug is required.
    """
    try:
        patient_label = "unknown"
        if request.patient and request.patient.fullName:
            patient_label = request.patient.fullName
        logger.info("Processing allergy-drug validation for patient: %s", patient_label)

        result = await allergy_drug_service.validate(request)

        logger.info(
            "Allergy-drug validation completed - Status: %s",
            result.quick_summary.overall_status,
        )
        return result

    except Exception as e:
        logger.error("Error in allergy-drug validation: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Allergy-drug validation failed: {str(e)}"
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
        reload=False,
        log_level="info"
    )
