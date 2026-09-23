"""Image (JPG/PNG scanned document) OCR extraction.

Primary path: gpt-4o vision (matches OCRParsingService's existing default demo path --
its local easyocr engine is optional/guarded and commented out of requirements.txt by
default because it pulls in ~2GB of torch). Local easyocr remains available as an
optional engine (OCR_ENGINE=easyocr) using the same guarded-import pattern.
"""
from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import easyocr  # type: ignore
except ImportError:  # pragma: no cover
    easyocr = None

_easyocr_reader = None


def _validate_image(file_bytes: bytes) -> None:
    try:
        Image.open(BytesIO(file_bytes)).verify()
    except UnidentifiedImageError as exc:
        raise ValueError("Unsupported or corrupted image file") from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Unsupported or corrupted image file: {exc}") from exc


def _extract_with_easyocr(file_bytes: bytes) -> str:
    global _easyocr_reader
    if easyocr is None:
        raise RuntimeError(
            "easyocr is not installed. Install it (see requirements.txt comment) or "
            "set OCR_ENGINE=vision to use the gpt-4o vision path instead."
        )
    import numpy as np

    if _easyocr_reader is None:
        logger.info("Initializing EasyOCR reader (languages=%s)", settings.ocr_languages_list)
        _easyocr_reader = easyocr.Reader(settings.ocr_languages_list, gpu=settings.ocr_gpu)

    image = Image.open(BytesIO(file_bytes)).convert("RGB")
    results = _easyocr_reader.readtext(np.array(image), detail=0)
    text = "\n".join(str(line).strip() for line in results if str(line).strip())
    if not text:
        raise ValueError("OCR failed to extract any text from the image")
    return text


def extract_image_text(file_bytes: bytes, content_type: str | None, ai_client) -> str:
    """Extract text from an image using the configured OCR engine.

    Args:
        file_bytes: Raw image bytes.
        content_type: MIME type reported by the upload (used as a hint for the vision call).
        ai_client: AIClient instance, used for the "vision" engine.

    Raises:
        ValueError: If the image is corrupted/unsupported or OCR extracts no text.
    """
    _validate_image(file_bytes)

    if settings.ocr_engine == "easyocr":
        return _extract_with_easyocr(file_bytes)

    # Default: gpt-4o vision OCR path.
    text = ai_client.extract_text_from_image(file_bytes, content_type or "image/jpeg")
    if not text or not text.strip():
        raise ValueError("OCR failed to extract any text from the image")
    return text
