"""API routes for OCR Parsing Service."""
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.models.schemas import (
    ExtractAndParseResponse,
    ExtractTextResponse,
    ParseTextRequest,
    ParseTextResponse,
)
from app.services.ocr_service import OCRService
from app.services.parsing_service import ParsingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ocr-parsing"])
ocr_service = OCRService()
parsing_service = ParsingService()


@router.post(
    "/extract-text",
    response_model=ExtractTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract text lines from an image",
)
async def extract_text(file: UploadFile = File(...)) -> ExtractTextResponse:
    try:
        image_bytes = await file.read()
        text_lines = ocr_service.extract_text_lines(image_bytes)
        return ExtractTextResponse(text_lines=text_lines, line_count=len(text_lines))
    except Exception as exc:
        logger.error("Failed OCR extraction for file=%s: %s", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OCR extraction failed: {exc}",
        ) from exc


@router.post(
    "/parse-text",
    response_model=ParseTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Parse text lines into structured JSON",
)
async def parse_text(request: ParseTextRequest) -> ParseTextResponse:
    try:
        raw_text = request.to_raw_text()
        structured_data = parsing_service.parse_text(raw_text)
        return ParseTextResponse(
            structured_data=structured_data,
            model=parsing_service.model,
        )
    except ValueError as exc:
        logger.error("Invalid parse output: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Parsing failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.error("Failed parsing request: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Parsing failed: {exc}",
        ) from exc


@router.post(
    "/extract-and-parse",
    response_model=ExtractAndParseResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract text from image and parse into structured JSON",
)
async def extract_and_parse(file: UploadFile = File(...)) -> ExtractAndParseResponse:
    try:
        image_bytes = await file.read()
        text_lines = ocr_service.extract_text_lines(image_bytes)
        raw_text = "\n".join(text_lines)
        structured_data = parsing_service.parse_text(raw_text)
        return ExtractAndParseResponse(
            text_lines=text_lines,
            structured_data=structured_data,
            model=parsing_service.model,
        )
    except ValueError as exc:
        logger.error("Invalid combined output for file=%s: %s", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Extract-and-parse failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.error("Failed combined request for file=%s: %s", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extract-and-parse failed: {exc}",
        ) from exc


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
)
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "ocr-parsing"}
