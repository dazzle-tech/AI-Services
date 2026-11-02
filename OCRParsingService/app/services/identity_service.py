"""Identity extraction service (OCR -> structured patient identity)."""

from __future__ import annotations

import logging
import re

from dataclasses import dataclass

from app.core.config import settings
from app.models.schemas import (
    Box,
    FieldSource,
    IdentityValidation,
    ImageInfo,
    OCRLineOut,
    OCRQuality,
    PatientIdentity,
)
from app.services.identity_parser import IdentityExtraction, extract_identity
from app.services.mrz_parser import MRZParseResult
from app.services.ocr_service import OCRService
from app.services.identity_validation import validate_identity
from app.services.parsing_service import ParsingService

logger = logging.getLogger(__name__)

_IDENTITY_FIELDS = ("full_name", "date_of_birth", "gender", "nationality", "document_number")


@dataclass(frozen=True)
class IdentityImageResult:
    identity: PatientIdentity
    quality: OCRQuality
    validation: IdentityValidation
    mrz_present: bool
    mrz_valid: bool | None
    text_lines: list[str]
    lines: list[OCRLineOut]
    field_sources: dict[str, FieldSource]
    image: ImageInfo


class IdentityService:
    def __init__(self) -> None:
        self.ocr = OCRService()
        self.parser = ParsingService()

    def extract_identity_from_image(self, image_bytes: bytes) -> IdentityImageResult:
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
        if settings.ocr_use_model_confidence_for_quality:
            low_average = avg_conf is not None and avg_conf < settings.ocr_min_avg_confidence
            low_minimum = min_conf is not None and min_conf < settings.ocr_low_confidence_threshold
            if low_average or low_minimum:
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
        llm_fields: list[str] = []
        if settings.identity_llm_fallback_enabled:
            identity, llm_fields = _llm_fill_gaps(identity, extraction.text_lines, self.parser)

        mrz_present = identity_extraction.mrz_present
        mrz_valid = identity_extraction.mrz_valid

        validation = validate_identity(identity, mrz_present=mrz_present, mrz_valid=mrz_valid)
        field_sources = _field_sources(
            identity_extraction,
            extraction.lines,
            mrz,
            llm_fields,
            validation,
        )
        lines = [] if not settings.ocr_return_boxes else [
            OCRLineOut(
                index=index,
                text=line.text,
                confidence=line.confidence,
                box=Box(x=line.box[0], y=line.box[1], w=line.box[2], h=line.box[3]),
                box_valid=line.box_valid,
                uncertain=line.uncertain,
            )
            for index, line in enumerate(extraction.lines)
        ]
        logger.info(
            "Identity extract lines=%d sourced=%d llm_fields=%d",
            len(extraction.text_lines),
            sum(1 for source in field_sources.values() if source.line_indices),
            len(llm_fields),
        )

        return IdentityImageResult(
            identity=identity,
            quality=quality,
            validation=validation,
            mrz_present=mrz_present,
            mrz_valid=mrz_valid,
            text_lines=extraction.text_lines,
            lines=lines,
            field_sources=field_sources,
            image=ImageInfo(
                original_width_px=extraction.original_width_px,
                original_height_px=extraction.original_height_px,
            ),
        )


def _normalize_full_name(full_name: str | None) -> str | None:
    if not full_name:
        return None
    value = re.sub(r"\s+", " ", full_name.strip())
    # Heuristic: title-case MRZ-style all-caps names.
    letters = re.sub(r"[^A-Z]", "", value.upper())
    if letters and value == value.upper() and len(letters) >= 6:
        return value.title()
    return value


def _min_line_confidence(indices: tuple[int, ...] | list[int], lines: list) -> float | None:
    values = [
        lines[index].confidence
        for index in indices
        if 0 <= index < len(lines) and lines[index].confidence is not None
    ]
    if not values:
        return None
    return min(values)


def _downgrade_level(level: str | None) -> str | None:
    if level == "high":
        return "medium"
    if level == "medium":
        return "low"
    return level


def _normalize_compare(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _mrz_visual_conflict(
    field_name: str,
    identity_extraction: IdentityExtraction,
    mrz: MRZParseResult | None,
) -> bool:
    if mrz is None or not identity_extraction.mrz_present:
        return False
    visual = identity_extraction.visual_values.get(field_name)
    mrz_value = getattr(mrz, field_name, None)
    if not visual or not mrz_value:
        return False
    return _normalize_compare(str(visual)) != _normalize_compare(str(mrz_value))


def _line_uncertain(indices: list[int], lines: list) -> bool:
    return any(
        0 <= index < len(lines) and lines[index].uncertain
        for index in indices
    )


def _sources_box_valid(indices: list[int], lines: list) -> bool:
    if not indices:
        return False
    return all(0 <= index < len(lines) and lines[index].box_valid for index in indices)


def _confidence_level(confidence: float | None) -> str | None:
    if confidence is None:
        return None
    if confidence >= settings.ocr_field_high_confidence:
        return "high"
    if confidence >= settings.ocr_field_medium_confidence:
        return "medium"
    return "low"


def _check_digit_covers(mrz: MRZParseResult, field_name: str) -> bool:
    validation = mrz.validation or {}
    if field_name == "date_of_birth":
        return validation.get("birth_date") is True
    if field_name == "document_number":
        if "document_number" in validation:
            return validation["document_number"] is True
        if "passport_number" in validation:
            return validation["passport_number"] is True
    return False


def _field_sources(
    identity_extraction: IdentityExtraction,
    lines: list,
    mrz: MRZParseResult | None,
    llm_fields: list[str],
    validation: IdentityValidation,
) -> dict[str, FieldSource]:
    sources: dict[str, FieldSource] = {}
    llm_set = set(llm_fields)
    flagged = {issue.field for issue in [*validation.errors, *validation.warnings]}
    for name in _IDENTITY_FIELDS:
        if name in llm_set:
            sources[name] = FieldSource(
                line_indices=[],
                source_kind="llm",
                confidence=None,
                level=None,
                box_valid=False,
            )
            continue
        indices = list(identity_extraction.field_sources.get(name, ()))
        kind = identity_extraction.field_source_kinds.get(name, "visual")
        if kind not in ("visual", "mrz", "llm"):
            kind = "visual"
        confidence = _min_line_confidence(indices, lines)
        level = _confidence_level(confidence)
        if (
            identity_extraction.mrz_valid
            and kind == "mrz"
            and mrz is not None
            and _check_digit_covers(mrz, name)
        ):
            level = "high"
        if _line_uncertain(indices, lines):
            level = "low"
        if name in flagged:
            level = _downgrade_level(level)
        if _mrz_visual_conflict(name, identity_extraction, mrz):
            level = "low"
        sources[name] = FieldSource(
            line_indices=indices,
            source_kind=kind,  # type: ignore[arg-type]
            confidence=confidence,
            level=level,  # type: ignore[arg-type]
            box_valid=_sources_box_valid(indices, lines),
        )
    return sources


def _llm_fill_gaps(
    identity: PatientIdentity,
    text_lines: list[str],
    parser: ParsingService,
) -> tuple[PatientIdentity, list[str]]:
    missing = [k for k in ("full_name", "date_of_birth", "gender", "nationality", "document_number") if getattr(identity, k) in (None, "")]
    if not missing:
        return identity, []

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
        return identity, []

    def pick(key: str) -> str | None:
        v = out.get(key)
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return None

    merged = identity.model_copy(deep=True)
    filled: list[str] = []
    if merged.full_name is None:
        full_name = _normalize_full_name(pick("full_name"))
        if full_name:
            merged.full_name = full_name
            filled.append("full_name")
    if merged.date_of_birth is None:
        date_of_birth = pick("date_of_birth")
        if date_of_birth:
            merged.date_of_birth = date_of_birth
            filled.append("date_of_birth")
    if merged.gender is None:
        g = pick("gender")
        if g in ("male", "female", "unspecified"):
            merged.gender = g  # type: ignore[assignment]
            filled.append("gender")
    if merged.nationality is None:
        nationality = pick("nationality")
        if nationality:
            merged.nationality = nationality
            filled.append("nationality")
    if merged.document_number is None:
        document_number = pick("document_number")
        if document_number:
            merged.document_number = document_number
            filled.append("document_number")

    if merged != identity:
        merged.extraction_source = "llm_fallback"
    return merged, filled
