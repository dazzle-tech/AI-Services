"""
Discharge Report Generation API
AI-powered discharge summary generation using OpenAI GPT-4
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import uvicorn

from models.schemas import (
    DischargeReportRequest,
    DischargeReportResponse
)
from services.discharge_report_service import discharge_report_generator
from services.discharge_sample_data import (
    get_sample_discharge_patient,
    get_sample_template
)
import config

# Initialize FastAPI app
app = FastAPI(
    title="Discharge Report Generation API",
    description="AI-powered discharge summary generation using OpenAI GPT-4",
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
        "service": "Discharge Report Generation API",
        "version": "1.0.0",
        "status": "operational",
        "ai_model": config.OPENAI_MODEL,
        "docs": "/docs",
        "endpoints": {
            "generate_report": "/discharge/generate-report",
            "quick_generate": "/discharge/quick-generate",
            "templates": "/discharge/templates",
            "sample_patients": "/discharge/sample-patients"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "openai_configured": bool(config.OPENAI_API_KEY),
        "generator_initialized": discharge_report_generator.initialized,
        "model": config.OPENAI_MODEL
    }


@app.post("/discharge/generate-report", response_model=DischargeReportResponse)
async def generate_discharge_report(req: DischargeReportRequest):
    """
    Generate discharge report using AI.
    
    **Full control version** - accepts complete patient record and clinical documentation.
    
    Args:
        - patient_record: Demographics, diagnosis, allergies, medications
        - clinical_documentation: Progress notes, admission notes, procedures, labs
        - report_template: Optional template structure
        - generation_mode: "template" or "freeform"
    
    Returns:
        Complete discharge report with structured sections and full text.
    """
    
    if not discharge_report_generator.initialized:
        discharge_report_generator.initialize()
    
    if not config.OPENAI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OpenAI API key not configured. Please set OPENAI_API_KEY in .env file."
        )
    
    result = await discharge_report_generator.generate_discharge_report(
        patient_record=req.patient_record,
        clinical_documentation=req.clinical_documentation,
        report_template=req.report_template,
        generation_mode=req.generation_mode
    )
    
    return result


@app.post("/discharge/quick-generate", response_model=DischargeReportResponse)
async def quick_discharge_generate(
    patient_id: str = "DISCH001",
    template_name: str = "standard",
    generation_mode: str = "template"
):
    """
    Quick discharge report generation using sample data.
    
    **Easy testing version** - uses pre-loaded sample patients.
    
    Query Parameters:
        - patient_id: Sample patient ID (default: DISCH001)
        - template_name: Template to use - "standard" or "cardiac" (default: standard)
        - generation_mode: "template" or "freeform" (default: template)
    
    Available sample patients: DISCH001
    """
    
    # Get sample data
    sample_data = get_sample_discharge_patient(patient_id)
    
    if not sample_data:
        raise HTTPException(
            status_code=404,
            detail=f"Sample patient '{patient_id}' not found. Available: DISCH001"
        )
    
    # Get template if needed
    template = None
    if generation_mode == "template":
        template = get_sample_template(template_name)
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Template '{template_name}' not found. Available: standard, cardiac"
            )
    
    # Initialize generator
    if not discharge_report_generator.initialized:
        discharge_report_generator.initialize()
    
    if not config.OPENAI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OpenAI API key not configured. Please set OPENAI_API_KEY in .env file."
        )
    
    # Generate report
    result = await discharge_report_generator.generate_discharge_report(
        patient_record=sample_data["patient"],
        clinical_documentation=sample_data["documentation"],
        report_template=template,
        generation_mode=generation_mode
    )
    
    return result


@app.get("/discharge/templates")
async def get_available_templates():
    """
    Get list of available discharge report templates.
    
    Returns information about each template including sections and format.
    """
    
    standard = get_sample_template("standard")
    cardiac = get_sample_template("cardiac")
    
    return {
        "total_templates": 2,
        "templates": [
            {
                "name": "standard",
                "display_name": standard.template_name,
                "description": "Standard discharge summary with all common sections",
                "format_type": standard.format_type,
                "sections": standard.sections,
                "required_fields": standard.required_fields
            },
            {
                "name": "cardiac",
                "display_name": cardiac.template_name,
                "description": "Cardiac-specific discharge summary with detailed cardiovascular sections",
                "format_type": cardiac.format_type,
                "sections": cardiac.sections,
                "required_fields": cardiac.required_fields
            }
        ]
    }


@app.get("/discharge/sample-patients")
async def get_discharge_sample_patients():
    """
    Get list of available sample patients for testing.
    
    Returns basic information about each sample patient.
    """
    
    return {
        "total_patients": 1,
        "patients": [
            {
                "patient_id": "DISCH001",
                "age": 58,
                "gender": "M",
                "description": "58-year-old male, Post-MI with PCI",
                "primary_diagnosis": "Acute ST-Elevation Myocardial Infarction (STEMI)",
                "admission_date": "2025-12-18",
                "discharge_date": "2025-12-23",
                "use_for_testing": "Ideal for testing cardiac discharge summaries"
            }
        ]
    }


@app.get("/discharge/patient-details/{patient_id}")
async def get_patient_details(patient_id: str):
    """
    Get complete details for a sample patient.
    
    Returns full patient record and clinical documentation.
    Useful for understanding the data structure.
    """
    
    sample_data = get_sample_discharge_patient(patient_id)
    
    if not sample_data:
        raise HTTPException(
            status_code=404,
            detail=f"Sample patient '{patient_id}' not found"
        )
    
    return {
        "patient_id": patient_id,
        "patient_record": sample_data["patient"].dict(),
        "clinical_documentation": sample_data["documentation"].dict()
    }


@app.on_event("startup")
async def startup():
    """Initialize services on startup."""
    print("\n" + "="*80)
    print("📝 DISCHARGE REPORT GENERATION API - STARTING")
    print("="*80)
    print(f"🤖 AI Model: {config.OPENAI_MODEL}")
    print(f"🌡️  Temperature: {config.OPENAI_TEMPERATURE}")
    print(f"📍 Server: http://{config.API_HOST}:{config.API_PORT}")
    print(f"📚 API Docs: http://localhost:{config.API_PORT}/docs")
    print(f"🧪 Sample Patients: 1 (DISCH001)")
    print(f"📋 Templates: 2 (standard, cardiac)")
    print("="*80 + "\n")
    
    discharge_report_generator.initialize()
    print("✅ Discharge Report Generator ready!")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    print("\n🛑 Discharge Report API shutdown complete.")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=config.API_RELOAD,
        log_level="info"
    )