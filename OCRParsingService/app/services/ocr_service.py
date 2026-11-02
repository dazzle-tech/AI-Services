"""Service for OCR extraction from images."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import base64
import logging
from io import BytesIO

import numpy as np
from PIL import Image, ImageOps
import cv2  # type: ignore

from app.ai.client import StructuredOutputClient
from app.core.config import settings

logger = logging.getLogger(__name__)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def map_polygon_to_upright(
    points: list[tuple[float, float]],
    rotation_degrees: int,
) -> list[tuple[float, float]]:
    """Map normalized points from a rotated OCR run back onto the upright image.

    rotation_degrees is the clockwise rotation that was applied before OCR
    (the same angles cv2.rotate uses: 0, 90, 180, 270).
    """
    deg = int(rotation_degrees) % 360
    mapped: list[tuple[float, float]] = []
    for x, y in points:
        if deg == 90:
            mx, my = y, 1.0 - x
        elif deg == 180:
            mx, my = 1.0 - x, 1.0 - y
        elif deg == 270:
            mx, my = 1.0 - y, x
        else:
            mx, my = x, y
        mapped.append((_clamp01(mx), _clamp01(my)))
    return mapped


_MAX_MODEL_SIDE_PX = 2048


def _jpeg_for_model(image: Image.Image) -> bytes:
    """Re-encode pixels as JPEG. The result has no EXIF or GPS from the upload."""
    longest = max(image.size)
    if longest > _MAX_MODEL_SIDE_PX:
        scale = _MAX_MODEL_SIDE_PX / longest
        resized = image.resize(
            (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
            Image.Resampling.LANCZOS,
        )
    else:
        resized = image
    buffer = BytesIO()
    resized.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


@dataclass(frozen=True)
class OCRLine:
    text: str
    confidence: float | None
    box: tuple[float, float, float, float]
    box_valid: bool = True
    uncertain: bool = False


_VISION_SYSTEM = (
    "You transcribe text that is visible in an image. Return JSON only. "
    "Do not translate, guess, or correct characters. "
    "Keep names, numbers, and spellings as printed. "
    "When a character is unreadable, write ? in its place and set uncertain to true."
)
_INVALID_BOX = (0.0, 0.0, 0.0, 0.0)


def _parse_box_numbers(box: object) -> tuple[float, float, float, float] | None:
    try:
        if isinstance(box, dict):
            raw = (box["x"], box["y"], box["w"], box["h"])
        elif isinstance(box, (list, tuple)) and len(box) >= 4:
            raw = (box[0], box[1], box[2], box[3])
        else:
            return None
        numbers = tuple(float(value) for value in raw)
    except (TypeError, ValueError, KeyError):
        return None
    if any(number != number for number in numbers):  # NaN
        return None
    return numbers  # type: ignore[return-value]


def assess_box(box: object) -> tuple[tuple[float, float, float, float], bool]:
    """Return a drawable box and whether it is safe to draw.

    A small overshoot of at most 0.02 past the right or bottom edge is clamped to 1.
    Anything else that cannot be drawn is returned as a zero box.
    """
    parsed = _parse_box_numbers(box)
    if parsed is None:
        return _INVALID_BOX, False
    x, y, w, h = parsed
    if w <= 0 or h <= 0 or h > 0.25 or (w * h) > 0.6:
        return _INVALID_BOX, False
    if x < 0 or y < 0 or x > 1 or y > 1:
        return _INVALID_BOX, False
    if x + w > 1.02 or y + h > 1.02:
        return _INVALID_BOX, False
    if x + w > 1:
        w = 1.0 - x
    if y + h > 1:
        h = 1.0 - y
    return (x, y, w, h), True


def _confidence_value(raw: object) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if value > 1.0 and value <= 100.0:
        value = value / 100.0
    return _clamp01(value)


def _uncertain_flag(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "1", "yes"}
    return bool(raw) if isinstance(raw, (int, float)) else False


def lines_from_vision_payload(payload: dict) -> list[OCRLine]:
    """Turn the vision model's JSON into OCR lines. Blank text is dropped."""
    raw_lines = payload.get("lines")
    if not isinstance(raw_lines, list):
        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            raw_lines = [{"text": line} for line in text.splitlines()]
        else:
            raw_lines = []

    lines: list[OCRLine] = []
    for item in raw_lines:
        if isinstance(item, str):
            text = item.strip()
            box, box_valid = _INVALID_BOX, False
            confidence = None
            uncertain = False
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            box, box_valid = assess_box(item.get("box"))
            confidence = _confidence_value(item.get("confidence"))
            uncertain = _uncertain_flag(item.get("uncertain"))
        else:
            continue
        if not text:
            continue
        lines.append(
            OCRLine(
                text=text,
                confidence=confidence,
                box=box,
                box_valid=box_valid,
                uncertain=uncertain,
            )
        )
    return lines


class OCRService:
    """Extract text lines from an image with the configured OpenAI vision model."""

    def __init__(self) -> None:
        self._client = StructuredOutputClient()

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
        lines: list[OCRLine] = field(default_factory=list)
        original_width_px: int = 0
        original_height_px: int = 0

    def extract(self, image_bytes: bytes) -> "OCRService.OCRExtraction":
        """Run OCR and return lines + confidence metrics."""
        try:
            image = Image.open(BytesIO(image_bytes))
            transposed = ImageOps.exif_transpose(image)
            if transposed is not None:
                image = transposed
            image = image.convert("RGB")
        except Exception as exc:  # PIL throws various exceptions for bad images
            raise ValueError("Unsupported or corrupted image input") from exc

        original_width, original_height = image.size
        image_np = np.array(image)
        extraction = self._recognize(image_np)
        extraction = replace(
            extraction,
            original_width_px=original_width,
            original_height_px=original_height,
            image_width_px=original_width,
            image_height_px=original_height,
            image_rotation_degrees=0,
        )
        logger.info(
            "OCR extracted %d lines (avg_conf=%s model=%s)",
            len(extraction.text_lines),
            None if extraction.avg_confidence is None else f"{extraction.avg_confidence:.3f}",
            settings.vision_model,
        )
        return extraction

    def extract_text_lines(self, image_bytes: bytes) -> list[str]:
        """Compatibility wrapper used by existing endpoints."""
        return self.extract(image_bytes).text_lines

    def _recognize(self, rgb_image: np.ndarray) -> "OCRService.OCRExtraction":
        height, width = rgb_image.shape[:2]
        blur_var, brightness_mean, contrast_std = self._image_quality_metrics(rgb_image)
        image = Image.fromarray(rgb_image)
        jpeg = _jpeg_for_model(image)
        data_url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        languages = ", ".join(settings.ocr_languages_list)
        payload = self._client.generate_vision_json(
            _VISION_SYSTEM,
            (
                "Read every visible text line from top to bottom. "
                f"The document may use these languages: {languages}. "
                "Return JSON "
                '{"lines":[{"text":"...","confidence":0.0,"uncertain":false,'
                '"box":{"x":0,"y":0,"w":0,"h":0}}]}. '
                "confidence is your certainty from 0 to 1. "
                "Set uncertain to true when any character is hard to read. "
                "Never guess or correct a character; write ? for each unreadable character. "
                "box is normalized to this image, origin top-left, each value from 0 to 1. "
                "One object per visual line. Omit blank lines."
            ),
            data_url,
            image_bytes=len(jpeg),
        )
        ocr_lines = lines_from_vision_payload(payload if isinstance(payload, dict) else {})
        confidences = [line.confidence for line in ocr_lines if line.confidence is not None]
        avg_conf = (sum(confidences) / len(confidences)) if confidences else None
        min_conf = min(confidences) if confidences else None
        return OCRService.OCRExtraction(
            text_lines=[line.text for line in ocr_lines],
            confidences=confidences,
            avg_confidence=avg_conf,
            min_confidence=min_conf,
            image_width_px=width,
            image_height_px=height,
            image_rotation_degrees=0,
            blur_variance=blur_var,
            brightness_mean=brightness_mean,
            contrast_std=contrast_std,
            lines=ocr_lines,
        )

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
