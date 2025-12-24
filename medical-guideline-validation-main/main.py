"""
Medical Guideline Validation API
AI-powered clinical decision support using OpenAI GPT-4
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from models.schemas import (
    GuidelineCheckRequest,
    GuidelineCheckResponse,
    QuickGuidelineCheckRequest
)
from services.guidelines_validator_service import openai_guideline_validator
from services.sample_clinical_data import get_patient_data, list_all_patients
import config

# Initialize FastAPI app
app = FastAPI(
    title="Medical Guideline Validation API",
    description="AI-powered clinical decision support using OpenAI GPT-4",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "service": "Medical Guideline Validation API",
        "version": "1.0.0",
        "status": "operational",
        "ai_model": config.OPENAI_MODEL,
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "openai_configured": bool(config.OPENAI_API_KEY),
        "validator_initialized": openai_guideline_validator.initialized
    }


@app.post("/validate/guideline-check", response_model=GuidelineCheckResponse)
async def validate_guideline_check(req: GuidelineCheckRequest):
    """
    AI-powered guideline validation check using OpenAI.
    
    This endpoint accepts complete patient data and validates active orders
    against clinical guidelines using GPT-4.
    """
    
    if not openai_guideline_validator.initialized:
        openai_guideline_validator.initialize()
    
    result = await openai_guideline_validator.validate_orders(
        patient_id=req.patient_id,
        active_orders=req.active_orders,
        clinical_context=req.clinical_context,
        patient_record=req.patient_record,
        specialty=req.specialty
    )
    
    return result


@app.post("/validate/quick-check", response_model=GuidelineCheckResponse)
async def quick_guideline_check(req: QuickGuidelineCheckRequest):
    """
    Quick AI-powered guideline check using sample patient data.
    
    Use this endpoint for testing with pre-loaded sample patients (P001, P002, P003).
    """
    
    patient_data = get_patient_data(req.patient_id)
    
    if not patient_data:
        raise HTTPException(
            status_code=404,
            detail=f"Patient {req.patient_id} not found in sample data. Available: P001, P002, P003"
        )
    
    if not openai_guideline_validator.initialized:
        openai_guideline_validator.initialize()
    
    result = await openai_guideline_validator.validate_orders(
        patient_id=req.patient_id,
        active_orders=patient_data["active_orders"],
        clinical_context=patient_data["clinical_context"],
        patient_record=patient_data["patient"],
        specialty=req.specialty
    )
    
    return result


@app.get("/sample-patients")
async def get_sample_patients():
    """Get list of available sample patients for testing."""
    patient_ids = list_all_patients()
    
    patients_info = []
    for pid in patient_ids:
        data = get_patient_data(pid)
        if data:
            patients_info.append({
                "patient_id": pid,
                "age": data["patient"]["age"],
                "gender": data["patient"]["gender"],
                "diagnosis": data["patient"]["current_diagnosis"],
                "department": data["patient"]["department"]
            })
    
    return {
        "total_patients": len(patients_info),
        "patients": patients_info
    }


@app.get("/patient-details/{patient_id}")
async def get_patient_details(patient_id: str):
    """Get complete details for a sample patient."""
    patient_data = get_patient_data(patient_id)
    
    if not patient_data:
        raise HTTPException(
            status_code=404,
            detail=f"Patient {patient_id} not found"
        )
    
    return patient_data


@app.on_event("startup")
async def startup():
    """Initialize services on startup."""
    print("\n" + "="*80)
    print("🏥 MEDICAL GUIDELINE VALIDATION API - STARTING")
    print("="*80)
    print(f"🤖 AI Model: {config.OPENAI_MODEL}")
    print(f"📍 Server: http://{config.API_HOST}:{config.API_PORT}")
    print(f"📚 API Docs: http://localhost:{config.API_PORT}/docs")
    print("="*80 + "\n")
    
    openai_guideline_validator.initialize()
    print("✅ All services initialized and ready!")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=config.API_RELOAD,
        log_level="info"
    )