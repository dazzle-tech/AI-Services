"""API routes for OCR Parsing Service."""
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.models.schemas import (
    ExtractAndParseResponse,
    ExtractTextResponse,
    IdentityExtractResponse,
    ParseTextRequest,
    ParseTextResponse,
)
from app.services.identity_service import IdentityService
from app.services.ocr_service import OCRService
from app.services.parsing_service import ParsingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ocr-parsing"])
ocr_service = OCRService()
parsing_service = ParsingService()
identity_service = IdentityService()


@router.post(
    "/extract-text",
    response_model=ExtractTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract text lines from an image",
)
async def extract_text(file: UploadFile = File(...)) -> ExtractTextResponse:
    try:
        image_bytes = await file.read()
        extraction = ocr_service.extract(image_bytes)
        return ExtractTextResponse(
            text_lines=extraction.text_lines,
            line_count=len(extraction.text_lines),
            avg_confidence=extraction.avg_confidence,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
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
        extraction = ocr_service.extract(image_bytes)
        raw_text = "\n".join(extraction.text_lines)
        structured_data = parsing_service.parse_text(raw_text)
        return ExtractAndParseResponse(
            text_lines=extraction.text_lines,
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


@router.post(
    "/identity/extract",
    response_model=IdentityExtractResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract structured patient identity from an ID/passport image",
)
async def extract_identity(
    file: UploadFile = File(...),
    strict_quality: bool = True,
) -> IdentityExtractResponse:
    try:
        image_bytes = await file.read()
        identity, quality, validation, mrz_present, mrz_valid, text_lines = identity_service.extract_identity_from_image(image_bytes)

        extracted_any = any(
            [
                identity.full_name,
                identity.date_of_birth,
                identity.gender,
                identity.nationality,
                identity.document_number,
            ]
        )
        if strict_quality and quality.is_low_quality:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "LOW_QUALITY_SCAN",
                    "message": "Low-quality scan; retake photo or disable strict_quality to get best-effort results.",
                    "quality": quality.model_dump(),
                },
            )
        if not extracted_any:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "NO_FIELDS_EXTRACTED",
                    "message": "No identity fields could be extracted; check cropping and orientation.",
                    "quality": quality.model_dump(),
                },
            )

        return IdentityExtractResponse(
            identity=identity,
            quality=quality,
            validation=validation,
            mrz_present=mrz_present,
            mrz_valid=mrz_valid,
            text_lines=text_lines,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed identity extraction for file=%s: %s", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Identity extraction failed: {exc}",
        ) from exc


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
)
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "ocr-parsing"}
