"""Field-to-line links for visual labels, MRZ, and LLM fallback."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.identity_parser import extract_identity
from app.services.identity_service import IdentityService
from app.services.mrz_parser import _check_digit
from app.services.ocr_service import OCRLine, OCRService


def test_same_line_label_and_value() -> None:
    identity, mrz = extract_identity(["Name: JANE DOE", "Sex: F"])
    assert mrz is None
    assert identity.full_name == "JANE DOE"
    assert identity.field_sources["full_name"] == (0,)
    assert identity.field_source_kinds["full_name"] == "visual"
    assert identity.field_sources["gender"] == (1,)
    assert identity.gender == "female"


def test_label_only_value_on_next_line_uses_original_indexes() -> None:
    identity, _ = extract_identity(["", "Date of Birth", "15/08/1991"])
    assert identity.date_of_birth == "1991-08-15"
    assert identity.field_sources["date_of_birth"] == (1, 2)
    assert identity.field_source_kinds["date_of_birth"] == "visual"


def test_surname_and_given_names_use_both_lines() -> None:
    identity, _ = extract_identity(["Surname: DOE", "Given Names: JANE ANN"])
    assert identity.full_name == "DOE JANE ANN"
    assert identity.field_sources["full_name"] == (0, 1)
    assert identity.field_source_kinds["full_name"] == "visual"


def _td3_lines() -> tuple[str, str]:
    line1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
    assert len(line1) == 44
    passport = "L898902C3"
    birth = "740812"
    expiry = "120415"
    personal = "ZE184226B<<<<<"
    assert len(personal) == 14
    passport_cd = _check_digit(passport)
    birth_cd = _check_digit(birth)
    expiry_cd = _check_digit(expiry)
    personal_cd = _check_digit(personal)
    composite = passport + passport_cd + birth + birth_cd + expiry + expiry_cd + personal + personal_cd
    line2 = (
        passport
        + passport_cd
        + "UTO"
        + birth
        + birth_cd
        + "F"
        + expiry
        + expiry_cd
        + personal
        + personal_cd
        + _check_digit(composite)
    )
    assert len(line2) == 44
    return line1, line2


def test_mrz_fields_point_at_mrz_lines() -> None:
    line1, line2 = _td3_lines()
    text_lines = ["Name: SOMEONE ELSE", "", line1, line2]
    identity, mrz = extract_identity(text_lines)
    assert mrz is not None and mrz.valid is True
    assert mrz.source_line_indices == (2, 3)
    assert identity.document_number == "L898902C3"
    assert identity.field_source_kinds["document_number"] == "mrz"
    assert identity.field_source_kinds["date_of_birth"] == "mrz"
    assert identity.field_source_kinds["full_name"] == "mrz"
    assert identity.field_sources["document_number"] == (2, 3)
    assert identity.field_sources["date_of_birth"] == (2, 3)
    assert identity.field_sources["full_name"] == (2, 3)


def test_llm_fallback_has_empty_line_indices(monkeypatch) -> None:
    monkeypatch.setattr(settings, "identity_llm_fallback_enabled", True)
    service = IdentityService()

    def _extract(_image_bytes: bytes):
        text_lines = ["unlabeled fragment"]
        return OCRService.OCRExtraction(
            text_lines=text_lines,
            confidences=[0.4],
            avg_confidence=0.4,
            min_confidence=0.4,
            image_width_px=800,
            image_height_px=700,
            image_rotation_degrees=0,
            blur_variance=120.0,
            brightness_mean=100.0,
            contrast_std=40.0,
            lines=[OCRLine(text_lines[0], 0.4, (0.1, 0.1, 0.3, 0.05))],
            original_width_px=800,
            original_height_px=700,
        )

    service.ocr.extract = _extract  # type: ignore[method-assign]
    service.parser.parse_prompt = lambda prompt: {  # type: ignore[method-assign]
        "full_name": "Ada Lovelace",
        "date_of_birth": "1815-12-10",
        "gender": "female",
        "nationality": "GBR",
        "document_number": "ABC12345",
    }
    result = service.extract_identity_from_image(b"unused")
    for name in ("full_name", "date_of_birth", "gender", "nationality", "document_number"):
        assert result.field_sources[name].line_indices == []
        assert result.field_sources[name].source_kind == "llm"
        assert result.field_sources[name].level is None


def test_valid_mrz_check_digits_mark_covered_fields_high(monkeypatch) -> None:
    monkeypatch.setattr(settings, "identity_llm_fallback_enabled", False)
    line1, line2 = _td3_lines()
    text_lines = [line1, line2, "extra", "padding"]
    service = IdentityService()

    def _extract(_image_bytes: bytes):
        lines = [
            OCRLine(text, 0.2, (0.0, index / 10, 0.8, 0.05))
            for index, text in enumerate(text_lines)
        ]
        return OCRService.OCRExtraction(
            text_lines=text_lines,
            confidences=[0.2, 0.2, 0.2, 0.2],
            avg_confidence=0.2,
            min_confidence=0.2,
            image_width_px=800,
            image_height_px=700,
            image_rotation_degrees=0,
            blur_variance=120.0,
            brightness_mean=100.0,
            contrast_std=40.0,
            lines=lines,
            original_width_px=800,
            original_height_px=700,
        )

    service.ocr.extract = _extract  # type: ignore[method-assign]
    result = service.extract_identity_from_image(b"unused")
    assert result.mrz_valid is True
    assert result.field_sources["document_number"].level == "high"
    assert result.field_sources["date_of_birth"].level == "high"
    assert result.field_sources["document_number"].confidence == 0.2


def _run(text_lines: list[str], lines: list[OCRLine]) -> object:
    service = IdentityService()

    def _extract(_image_bytes: bytes):
        confidences = [line.confidence for line in lines if line.confidence is not None]
        return OCRService.OCRExtraction(
            text_lines=text_lines,
            confidences=confidences,
            avg_confidence=(sum(confidences) / len(confidences)) if confidences else None,
            min_confidence=min(confidences) if confidences else None,
            image_width_px=800,
            image_height_px=700,
            image_rotation_degrees=0,
            blur_variance=120.0,
            brightness_mean=100.0,
            contrast_std=40.0,
            lines=lines,
            original_width_px=800,
            original_height_px=700,
        )

    service.ocr.extract = _extract  # type: ignore[method-assign]
    return service.extract_identity_from_image(b"unused")


def test_uncertain_line_sets_field_level_low(monkeypatch) -> None:
    monkeypatch.setattr(settings, "identity_llm_fallback_enabled", False)
    text = ["Name: JANE DOE"]
    result = _run(
        text,
        [OCRLine(text[0], 0.95, (0.1, 0.1, 0.4, 0.04), box_valid=True, uncertain=True)],
    )
    assert result.field_sources["full_name"].level == "low"
    assert result.lines[0].uncertain is True


def test_validation_warning_downgrades_level(monkeypatch) -> None:
    monkeypatch.setattr(settings, "identity_llm_fallback_enabled", False)
    text = ["Nationality: CANADA"]
    result = _run(
        text,
        [OCRLine(text[0], 0.95, (0.1, 0.1, 0.4, 0.04), box_valid=True, uncertain=False)],
    )
    assert result.field_sources["nationality"].level == "medium"


def test_mrz_visual_mismatch_sets_level_low(monkeypatch) -> None:
    monkeypatch.setattr(settings, "identity_llm_fallback_enabled", False)
    line1, line2 = _td3_lines()
    text = ["Name: SOMEONE ELSE", line1, line2, "padding"]
    lines = [
        OCRLine(text[0], 0.95, (0.1, 0.05, 0.4, 0.04), box_valid=True, uncertain=False),
        OCRLine(text[1], 0.95, (0.05, 0.7, 0.9, 0.04), box_valid=True, uncertain=False),
        OCRLine(text[2], 0.95, (0.05, 0.76, 0.9, 0.04), box_valid=True, uncertain=False),
        OCRLine(text[3], 0.95, (0.1, 0.2, 0.2, 0.04), box_valid=True, uncertain=False),
    ]
    result = _run(text, lines)
    assert result.mrz_present is True
    assert result.field_sources["full_name"].level == "low"
    assert result.field_sources["document_number"].level == "high"


def test_model_confidence_is_not_a_quality_gate_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ocr_use_model_confidence_for_quality", False)
    monkeypatch.setattr(settings, "identity_llm_fallback_enabled", False)
    text = ["Name: JANE DOE", "Sex: F", "Passport No: AB123456"]
    lines = [
        OCRLine(item, 0.1, (0.1, 0.1 + index * 0.05, 0.4, 0.04))
        for index, item in enumerate(text)
    ]
    result = _run(text, lines)
    assert result.quality.avg_confidence == pytest.approx(0.1)
    assert result.quality.is_low_quality is False
    assert not any("Low OCR confidence" in warning for warning in result.quality.warnings)
