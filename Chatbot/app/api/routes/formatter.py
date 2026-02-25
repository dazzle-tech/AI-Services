"""Formatter API routes."""
import logging
from fastapi import APIRouter
from app.models.schemas import FormatterRequest, FormatterResponse
from app.services.formatting import FormattingService

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize service
_formatting_service = FormattingService()


@router.post("/format", response_model=FormatterResponse)
@router.post("/format_results", response_model=FormatterResponse)
def format_endpoint(payload: FormatterRequest) -> FormatterResponse:
    """Format database result into human-like summary."""
    logger.info("🚀 /format request received")
    return _formatting_service.format(payload)


@router.get("/")
def root():
    """Root endpoint."""
    return {"ok": True, "service": "MedAI Humanized Formatter (v4.0.0)"}



