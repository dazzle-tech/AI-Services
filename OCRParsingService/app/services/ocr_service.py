"""Service for OCR extraction from images."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from io import BytesIO

import numpy as np
from PIL import Image
import cv2  # type: ignore

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import easyocr  # type: ignore
except ImportError:  # pragma: no cover
    easyocr = None


class OCRService:
    """Extract text lines from an image using EasyOCR."""

    def __init__(self) -> None:
        self._reader: easyocr.Reader | None = None

    @property
    def reader(self) -> easyocr.Reader:
        if easyocr is None:
            raise RuntimeError(
                "EasyOCR is not installed. Install dependencies with: py -m pip install -r requirements.txt"
            )
        if self._reader is None:
            logger.info("Initializing EasyOCR reader with languages=%s, gpu=%s", settings.ocr_languages_list, settings.ocr_gpu)
            self._reader = easyocr.Reader(settings.ocr_languages_list, gpu=settings.ocr_gpu)
            logger.info("EasyOCR reader initialized")
        return self._reader

    @dataclass(frozen=True)
    class OCRExtraction:
        text_lines: list[str]
        confidences: list[float]
        avg_confidence: float | None
        min_confidence: float | None
        image_width_px: int
        image_height_px: int
        image_rotation_degrees: int
        blur_variance: float | None
        brightness_mean: float | None
        contrast_std: float | None

    def extract(self, image_bytes: bytes) -> "OCRService.OCRExtraction":
        """Run OCR and return lines + confidence metrics."""
        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:  # PIL throws various exceptions for bad images
            raise ValueError("Unsupported or corrupted image input") from exc

        image_np = np.array(image)
        h, w = image_np.shape[:2]

        # Baseline run at 0 degrees (with optional preprocessing).
        best = self._run_easyocr(image_np, rotation_degrees=0)
        if settings.ocr_preprocess:
            processed = self._preprocess_for_ocr(image_np)
            candidate = self._run_easyocr(processed, rotation_degrees=0)
            best = self._pick_better(best, candidate)

        # If baseline looks weak, try additional rotations (helps with upside-down/sideways scans).
        if settings.ocr_try_rotations_on_low_quality and self._looks_low_quality(best):
            for deg in settings.ocr_rotations_list:
                if deg % 360 == 0:
                    continue
                rotated = self._rotate_rgb(image_np, deg)
                cand = self._run_easyocr(rotated, rotation_degrees=deg)
                best = self._pick_better(best, cand)

                if settings.ocr_preprocess:
                    rotated_processed = self._preprocess_for_ocr(rotated)
                    cand2 = self._run_easyocr(rotated_processed, rotation_degrees=deg)
                    best = self._pick_better(best, cand2)

        logger.info(
            "OCR extracted %d lines (avg_conf=%s)",
            len(best.text_lines),
            None if best.avg_confidence is None else f"{best.avg_confidence:.3f}",
        )
        return best

    def extract_text_lines(self, image_bytes: bytes) -> list[str]:
        """Compatibility wrapper used by existing endpoints."""
        return self.extract(image_bytes).text_lines

    def _score(self, extraction: "OCRService.OCRExtraction") -> float:
        avg = extraction.avg_confidence or 0.0
        lines = min(len(extraction.text_lines), 25)
        return avg + 0.04 * lines

    def _pick_better(
        self,
        left: "OCRService.OCRExtraction",
        right: "OCRService.OCRExtraction",
    ) -> "OCRService.OCRExtraction":
        return right if self._score(right) > self._score(left) else left

    def _looks_low_quality(self, extraction: "OCRService.OCRExtraction") -> bool:
        if len(extraction.text_lines) < max(4, settings.ocr_min_lines):
            return True
        if extraction.avg_confidence is not None and extraction.avg_confidence < max(0.45, settings.ocr_min_avg_confidence):
            return True
        return False

    def _run_easyocr(self, rgb_image: np.ndarray, *, rotation_degrees: int) -> "OCRService.OCRExtraction":
        h, w = rgb_image.shape[:2]
        blur_var, brightness_mean, contrast_std = self._image_quality_metrics(rgb_image)
        results = self.reader.readtext(rgb_image, detail=1)
        lines: list[str] = []
        confidences: list[float] = []
        for item in results:
            # item: (bbox, text, confidence)
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            text = str(item[1]).strip()
            conf = float(item[2]) if item[2] is not None else None
            if not text:
                continue
            lines.append(text)
            if conf is not None:
                confidences.append(max(0.0, min(1.0, conf)))

        avg_conf = (sum(confidences) / len(confidences)) if confidences else None
        min_conf = min(confidences) if confidences else None
        return OCRService.OCRExtraction(
            text_lines=lines,
            confidences=confidences,
            avg_confidence=avg_conf,
            min_confidence=min_conf,
            image_width_px=w,
            image_height_px=h,
            image_rotation_degrees=int(rotation_degrees % 360),
            blur_variance=blur_var,
            brightness_mean=brightness_mean,
            contrast_std=contrast_std,
        )

    def _preprocess_for_ocr(self, rgb_image: np.ndarray) -> np.ndarray:
        """Lightweight preprocessing for low-quality scans (denoise + threshold)."""
        # Convert RGB -> GRAY
        gray = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)

        # Scale up small images (helps OCR on low-res mobile scans)
        h, w = gray.shape[:2]
        if max(h, w) < 900:
            scale = 2.0
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

        gray = cv2.bilateralFilter(gray, d=7, sigmaColor=50, sigmaSpace=50)
        gray = cv2.fastNlMeansDenoising(gray, h=10)

        # Otsu binarization often helps with glare/shadows.
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Convert back to 3-channel RGB for EasyOCR.
        rgb = cv2.cvtColor(th, cv2.COLOR_GRAY2RGB)
        return rgb

    def _rotate_rgb(self, rgb_image: np.ndarray, degrees: int) -> np.ndarray:
        degrees = int(degrees % 360)
        if degrees == 0:
            return rgb_image
        if degrees == 90:
            return cv2.rotate(rgb_image, cv2.ROTATE_90_CLOCKWISE)
        if degrees == 180:
            return cv2.rotate(rgb_image, cv2.ROTATE_180)
        if degrees == 270:
            return cv2.rotate(rgb_image, cv2.ROTATE_90_COUNTERCLOCKWISE)

        # Fallback for uncommon angles (shouldn't be used in normal configs)
        h, w = rgb_image.shape[:2]
        center = (w / 2.0, h / 2.0)
        mat = cv2.getRotationMatrix2D(center, degrees, 1.0)
        return cv2.warpAffine(rgb_image, mat, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    def _image_quality_metrics(self, rgb_image: np.ndarray) -> tuple[float | None, float | None, float | None]:
        try:
            gray = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2GRAY)
            lap = cv2.Laplacian(gray, cv2.CV_64F)
            blur_var = float(lap.var())
            brightness_mean = float(np.mean(gray))
            contrast_std = float(np.std(gray))
            return blur_var, brightness_mean, contrast_std
        except Exception:
            return None, None, None
