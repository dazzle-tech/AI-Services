"""API routes for the Medical Document Processor service."""
import json
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError

from app.core.config import settings
from app.models.schemas import ExistingDocumentSummary, PatientInfo, ProcessDocumentResponse
from app.services.document_processor_service import DocumentProcessorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["medical-document-processor"])

# Initialize service
document_processor_service = DocumentProcessorService()


def _parse_patient(patient_json: str) -> PatientInfo:
    try:
        data = json.loads(patient_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"`patient` must be a valid JSON object: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("`patient` must be a JSON object")
    try:
        return PatientInfo(**data)
    except ValidationError as exc:
        raise ValueError(f"Invalid `patient` payload: {exc}") from exc


def _parse_existing_documents(existing_documents_json: Optional[str]) -> list[ExistingDocumentSummary]:
    if not existing_documents_json or not existing_documents_json.strip():
        return []
    try:
        data = json.loads(existing_documents_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"`existing_documents` must be valid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("`existing_documents` must be a JSON array")
    try:
        return [ExistingDocumentSummary(**item) for item in data]
    except ValidationError as exc:
        raise ValueError(f"Invalid `existing_documents` payload: {exc}") from exc


@router.post(
    "/process-document",
    response_model=ProcessDocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Run a medical document through the validation -> relevance -> "
    "translation -> structured-formatting pipeline",
    description="""
    Accepts an uploaded medical document (PDF, DOCX, TXT, CSV, or JPG/PNG scan) plus
    patient metadata, and runs it through a four-step pipeline:
    1. File & patient-data validation (stops here if the document doesn't match the patient).
    2. Relevance check against configurable per-document-type recency windows (stops here
       if the document is outdated/superseded).
    3. Language detection, with translation if requested and the target language differs.
    4. Document-type classification and structured formatting.

    Returns a single response object regardless of where the pipeline stopped.
    """,
)
async def process_document(
    file: UploadFile = File(..., description="The medical document to process"),
    patient: str = Form(..., description="JSON-encoded patient object: patient_id, full_name, sex, date_of_birth"),
    translate: bool = Form(False, description="Translate the document if its language differs from target_language"),
    target_language: Optional[str] = Form(None, description="Defaults to the service's configured default language"),
    existing_documents: Optional[str] = Form(
        None, description="Optional JSON array of {document_type, document_date} for supersede checks"
    ),
) -> ProcessDocumentResponse:
    try:
        patient_obj = _parse_patient(patient)
        existing_documents_obj = _parse_existing_documents(existing_documents)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Uploaded file is empty")

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_upload_size_mb}MB upload limit",
        )

    try:
        return document_processor_service.process(
            file_bytes=file_bytes,
            filename=file.filename,
            content_type=file.content_type,
            patient=patient_obj,
            translate=translate,
            target_language=target_language or settings.default_target_language,
            existing_documents=existing_documents_obj,
        )
    except ValueError as exc:
        logger.error("Validation error processing document: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Processing failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error processing document: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal server error: {exc}"
        ) from exc


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
)
async def health_check():
    """Health check endpoint with OpenAI API status."""
    openai_configured = bool(settings.openai_api_key)

    api_accessible = False
    if openai_configured:
        try:
            api_key = settings.openai_api_key
            api_accessible = len(api_key) > 8
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI API key validation failed: %s", exc)
            api_accessible = False

    return {
        "status": "healthy" if (openai_configured and api_accessible) else "degraded",
        "service": "medical-document-processor",
        "provider": "openai",
        "openai_configured": openai_configured,
        "api_accessible": api_accessible,
        "model": settings.openai_model if openai_configured else None,
        "ocr_engine": settings.ocr_engine,
        "version": settings.api_version,
    }
