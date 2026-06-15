"""Identity extraction service (OCR -> structured patient identity)."""

from __future__ import annotations

import logging
import re

from app.core.config import settings
from app.models.schemas import IdentityValidation, OCRQuality, PatientIdentity
from app.services.identity_parser import extract_identity
from app.services.ocr_service import OCRService
from app.services.identity_validation import validate_identity
from app.services.parsing_service import ParsingService

logger = logging.getLogger(__name__)


class IdentityService:
    def __init__(self) -> None:
        self.ocr = OCRService()
        self.parser = ParsingService()

    def extract_identity_from_image(
        self, image_bytes: bytes
    ) -> tuple[PatientIdentity, OCRQuality, IdentityValidation, bool, bool | None, list[str]]:
        extraction = self.ocr.extract(image_bytes)

        confidences = extraction.confidences
        avg_conf = extraction.avg_confidence
        min_conf = extraction.min_confidence
        low_fraction = None
        if confidences:
            low = [c for c in confidences if c < settings.ocr_low_confidence_threshold]
            low_fraction = len(low) / len(confidences)

        warnings: list[str] = []
        is_low_quality = False

        short_side = min(extraction.image_width_px, extraction.image_height_px)
        if short_side < settings.ocr_min_image_short_side_px:
            warnings.append(
                f"Low resolution ({extraction.image_width_px}x{extraction.image_height_px}); capture a closer, higher-res image."
            )
            is_low_quality = True

        if len(extraction.text_lines) < settings.ocr_min_lines:
            warnings.append("Too few readable text lines detected; check focus/cropping.")
            is_low_quality = True
        if avg_conf is not None and avg_conf < settings.ocr_min_avg_confidence:
            warnings.append("Low OCR confidence; consider retaking the photo with better lighting.")
            is_low_quality = True
        if low_fraction is not None and low_fraction > settings.ocr_low_confidence_fraction_threshold:
            warnings.append("Many low-confidence OCR segments; glare/blur suspected.")
            is_low_quality = True
        if extraction.blur_variance is not None and extraction.blur_variance < settings.ocr_min_blur_variance:
            warnings.append("Image appears blurry; stabilize camera and refocus.")
            is_low_quality = True
        if extraction.brightness_mean is not None and (
            extraction.brightness_mean < settings.ocr_brightness_min
            or extraction.brightness_mean > settings.ocr_brightness_max
        ):
            warnings.append("Poor lighting detected (too dark/bright); retake photo with even light.")
            is_low_quality = True
        if extraction.contrast_std is not None and extraction.contrast_std < settings.ocr_contrast_std_min:
            warnings.append("Low contrast detected; avoid glare and ensure text is readable.")
            is_low_quality = True

        quality = OCRQuality(
            avg_confidence=avg_conf,
            min_confidence=min_conf,
            low_confidence_fraction=low_fraction,
            image_width_px=extraction.image_width_px,
            image_height_px=extraction.image_height_px,
            image_rotation_degrees=extraction.image_rotation_degrees,
            blur_variance=extraction.blur_variance,
            brightness_mean=extraction.brightness_mean,
            contrast_std=extraction.contrast_std,
            is_low_quality=is_low_quality,
            warnings=warnings,
        )

        identity_extraction, mrz = extract_identity(extraction.text_lines)

        identity = PatientIdentity(
            full_name=_normalize_full_name(identity_extraction.full_name),
            date_of_birth=identity_extraction.date_of_birth,
            gender=identity_extraction.gender,  # type: ignore[arg-type]
            nationality=identity_extraction.nationality,
            document_number=identity_extraction.document_number,
            document_type=identity_extraction.document_type,  # type: ignore[arg-type]
            extraction_source=identity_extraction.extraction_source,  # type: ignore[arg-type]
        )

        # Optional LLM fallback to fill gaps (disabled by default).
        if settings.identity_llm_fallback_enabled:
            identity = _llm_fill_gaps(identity, extraction.text_lines, self.parser)

        mrz_present = identity_extraction.mrz_present
        mrz_valid = identity_extraction.mrz_valid

        validation = validate_identity(identity, mrz_present=mrz_present, mrz_valid=mrz_valid)

        return identity, quality, validation, mrz_present, mrz_valid, extraction.text_lines


def _normalize_full_name(full_name: str | None) -> str | None:
    if not full_name:
        return None
    value = re.sub(r"\s+", " ", full_name.strip())
    # Heuristic: title-case MRZ-style all-caps names.
    letters = re.sub(r"[^A-Z]", "", value.upper())
    if letters and value == value.upper() and len(letters) >= 6:
        return value.title()
    return value


def _llm_fill_gaps(identity: PatientIdentity, text_lines: list[str], parser: ParsingService) -> PatientIdentity:
    missing = [k for k in ("full_name", "date_of_birth", "gender", "nationality", "document_number") if getattr(identity, k) in (None, "")]
    if not missing:
        return identity

    raw_text = "\n".join(line.strip() for line in text_lines if line.strip())
    prompt = (
        "Extract patient identity fields from this OCR text and return STRICT JSON with keys:\n"
        "full_name, date_of_birth (YYYY-MM-DD if possible), gender (male|female|unspecified), nationality, document_number.\n"
        "If unknown, use empty string. Return ONLY JSON.\n\n"
        f"OCR Text:\n{raw_text}\n"
    )

    try:
        out = parser.parse_prompt(prompt)
    except Exception:
        return identity

    def pick(key: str) -> str | None:
        v = out.get(key)
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return None

    merged = identity.model_copy(deep=True)
    if merged.full_name is None:
        merged.full_name = _normalize_full_name(pick("full_name"))
    if merged.date_of_birth is None:
        merged.date_of_birth = pick("date_of_birth")
    if merged.gender is None:
        g = pick("gender")
        if g in ("male", "female", "unspecified"):
            merged.gender = g  # type: ignore[assignment]
    if merged.nationality is None:
        merged.nationality = pick("nationality")
    if merged.document_number is None:
        merged.document_number = pick("document_number")

    if merged != identity:
        merged.extraction_source = "llm_fallback"
    return merged
