"""
Radiology Template Selection & Autofill Service.

Two-stage pipeline:
  1. Template Selection (RAG over a managed template repository, or static override)
  2. Autofill (LLM populates the selected template from raw input)
"""

import logging
import uuid

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import config
from data.sample_inputs import get_sample, list_samples
from models.schemas import (
    AutofillRequest,
    AutofillResponse,
    SelectAndFillRequest,
    SelectAndFillResponse,
    SelectionMethod,
    SelectTemplateRequest,
    SelectTemplateResponse,
    TemplateCandidate,
)
from services.autofill_service import AutofillService
from services.rag_selector import RAGTemplateSelector
from services.template_repository import TemplateRepository

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Radiology Template Selection & Autofill",
    description=(
        "Selects the most relevant radiology report template via RAG (or a static "
        "override), then autofills the template from a clinician's dictation."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

repository = TemplateRepository(templates_dir=config.TEMPLATES_DIR)
selector = RAGTemplateSelector(
    repository=repository,
    vector_store_path=config.VECTOR_STORE_PATH,
    embedding_model=config.EMBEDDING_MODEL,
)
autofill_service = AutofillService(
    repository=repository,
    openai_api_key=config.OPENAI_API_KEY,
    model=config.OPENAI_MODEL,
    temperature=config.OPENAI_TEMPERATURE,
    mock_llm=config.MOCK_LLM,
)


# --- Lifecycle ---------------------------------------------------------------

@app.on_event("startup")
async def startup() -> None:
    logger.info("=" * 80)
    logger.info("RADIOLOGY TEMPLATE AUTOFILL SERVICE — STARTING")
    logger.info("=" * 80)
    logger.info("AI Model: %s (mock=%s)", config.OPENAI_MODEL, config.MOCK_LLM)
    logger.info("Embedding model: %s", config.EMBEDDING_MODEL)
    logger.info("Templates dir: %s", config.TEMPLATES_DIR)
    logger.info("Vector store: %s", config.VECTOR_STORE_PATH)
    logger.info("Server: http://%s:%s", config.API_HOST, config.API_PORT)
    logger.info("Docs: http://localhost:%s/docs", config.API_PORT)
    logger.info("=" * 80)

    repository.load()
    selector.initialize()
    autofill_service.initialize()
    logger.info("Service ready (%d templates indexed).", len(repository.all()))


# --- Meta endpoints ----------------------------------------------------------

@app.get("/")
async def root():
    return {
        "service": "Radiology Template Selection & Autofill",
        "version": "1.0.0",
        "status": "operational",
        "ai_model": config.OPENAI_MODEL,
        "mock_llm": config.MOCK_LLM,
        "templates_loaded": len(repository.all()),
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "openai_configured": bool(config.OPENAI_API_KEY),
        "mock_llm": config.MOCK_LLM,
        "rag_initialized": selector.initialized,
        "templates_loaded": len(repository.all()),
    }


# --- Template repository -----------------------------------------------------

@app.get("/templates")
async def list_templates():
    return {"total": len(repository.all()), "templates": repository.summaries()}


@app.get("/templates/{template_id}")
async def get_template(template_id: str):
    template = repository.get(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found.")
    return template


# --- Sample inputs (handy for quick testing) ---------------------------------

@app.get("/samples")
async def list_sample_inputs():
    return {"samples": list_samples()}


@app.get("/samples/{key}")
async def get_sample_input(key: str):
    sample = get_sample(key)
    if not sample:
        raise HTTPException(status_code=404, detail=f"Sample '{key}' not found.")
    return sample


# --- Stage 1: Template Selection ---------------------------------------------

@app.post("/select-template", response_model=SelectTemplateResponse)
async def select_template(req: SelectTemplateRequest):
    request_id = req.request_id or f"req-{uuid.uuid4().hex[:8]}"

    if req.use_static_template:
        if not req.static_template_id:
            raise HTTPException(
                status_code=400,
                detail="use_static_template=true requires `static_template_id`.",
            )
        template = repository.get(req.static_template_id)
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Static template '{req.static_template_id}' not found.",
            )
        return SelectTemplateResponse(
            request_id=request_id,
            selection_method=SelectionMethod.STATIC,
            selected_template_id=template.template_id,
            selected_template_name=repository.get_localized_template_name(template, req.OutputLanguage),
            intent_profile=None,
            candidates=[
                TemplateCandidate(
                    template_id=template.template_id,
                    name=repository.get_localized_template_name(template, req.OutputLanguage),
                    modality=template.modality,
                    body_region=template.body_region,
                    score=1.0,
                )
            ],
        )

    try:
        candidates = selector.select(
            req.input_data,
            top_k=req.top_k,
            patient_context=(getattr(req, "patient_context", None) or {}),
            output_language=req.OutputLanguage,
        )
    except TypeError:
        candidates = selector.select(req.input_data, top_k=req.top_k, output_language=req.OutputLanguage)
    if not candidates:
        raise HTTPException(status_code=500, detail="No template candidates returned.")
    best = candidates[0]
    best_template = repository.get(best.template_id)

    return SelectTemplateResponse(
        request_id=request_id,
        selection_method=SelectionMethod.RAG,
        selected_template_id=best.template_id,
        selected_template_name=(
            repository.get_localized_template_name(best_template, req.OutputLanguage)
            if best_template is not None
            else best.name
        ),
        intent_profile=selector.derive_intent_profile(req.input_data),
        candidates=candidates,
    )


# --- Stage 2: Autofill -------------------------------------------------------

@app.post("/autofill", response_model=AutofillResponse)
async def autofill(req: AutofillRequest):
    template = repository.get(req.template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{req.template_id}' not found.")

    return await autofill_service.autofill(
        template=template,
        input_data=req.input_data,
        request_id=req.request_id or f"req-{uuid.uuid4().hex[:8]}",
        patient_context=req.patient_context,
        output_language=req.OutputLanguage,
    )


# --- Combined: select + autofill in one call ---------------------------------

@app.post("/select-and-fill", response_model=SelectAndFillResponse)
async def select_and_fill(req: SelectAndFillRequest):
    request_id = req.request_id or f"req-{uuid.uuid4().hex[:8]}"

    selection = await select_template(
        SelectTemplateRequest(
            request_id=request_id,
            input_data=req.input_data,
            use_static_template=req.use_static_template,
            static_template_id=req.static_template_id,
            top_k=req.top_k,
            patient_context=req.patient_context,
            OutputLanguage=req.OutputLanguage,
        )
    )

    fill = await autofill(
        AutofillRequest(
            request_id=request_id,
            template_id=selection.selected_template_id,
            input_data=req.input_data,
            patient_context=req.patient_context,
            OutputLanguage=req.OutputLanguage,
        )
    )

    return SelectAndFillResponse(**fill.model_dump())


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=config.API_RELOAD,
        log_level="info",
    )
