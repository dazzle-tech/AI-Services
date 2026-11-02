"""API routes for OCR Parsing Service."""
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status

try:
    from openai import APIConnectionError, APITimeoutError, AuthenticationError, RateLimitError
except ImportError:  # pragma: no cover
    class AuthenticationError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    class APIConnectionError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

from app.ai.client import OCRUnavailable
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

_PROVIDER_ERRORS = (OCRUnavailable, AuthenticationError, RateLimitError, APIConnectionError, APITimeoutError)
_UNAVAILABLE = {
    "code": "OCR_UNAVAILABLE",
    "message": "The reading service is temporarily unavailable.",
}


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
        logger.error("OCR extraction failed type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OCR extraction failed",
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
    except ValueError:
        logger.error("Invalid parse output type=ValueError")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Parsing failed",
        )
    except Exception as exc:
        logger.error("Parsing failed type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Parsing failed",
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
    except ValueError:
        logger.error("Extract-and-parse failed type=ValueError")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Extract-and-parse failed",
        )
    except Exception as exc:
        logger.error("Extract-and-parse failed type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Extract-and-parse failed",
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
        result = identity_service.extract_identity_from_image(image_bytes)
        identity = result.identity
        quality = result.quality
        validation = result.validation
        mrz_present = result.mrz_present
        mrz_valid = result.mrz_valid
        text_lines = result.text_lines

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
            lines=result.lines,
            field_sources=result.field_sources,
            image=result.image,
        )
    except _PROVIDER_ERRORS as exc:
        logger.error("Identity extraction unavailable type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_UNAVAILABLE,
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Identity extraction failed type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Identity extraction failed",
        ) from exc


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
)
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "ocr-parsing"}
