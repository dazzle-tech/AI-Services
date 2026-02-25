"""Service for OCR extraction from images."""
import logging
from io import BytesIO

import easyocr
import numpy as np
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)


class OCRService:
    """Extract text lines from an image using EasyOCR."""

    def __init__(self) -> None:
        self._reader: easyocr.Reader | None = None

    @property
    def reader(self) -> easyocr.Reader:
        if self._reader is None:
            logger.info("Initializing EasyOCR reader with languages=%s, gpu=%s", settings.ocr_languages_list, settings.ocr_gpu)
            self._reader = easyocr.Reader(settings.ocr_languages_list, gpu=settings.ocr_gpu)
            logger.info("EasyOCR reader initialized")
        return self._reader

    def extract_text_lines(self, image_bytes: bytes) -> list[str]:
        """Run OCR and return cleaned text lines."""
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image_np = np.array(image)
        results = self.reader.readtext(image_np, detail=0)
        lines = [line.strip() for line in results if line.strip()]
        logger.info("OCR extracted %d non-empty lines", len(lines))
        return lines
