"""Structured fields are matched back to the OCR line that printed them."""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.api import routes
from app.services.field_positions import locate_field_positions
from app.services.ocr_service import OCRLine, OCRService
from main import app

client = TestClient(app)

_CARD = [
    ("UNITED STATES OF AMERICA", 0.10, 0.02),
    ("PASSPORT CARD", 0.10, 0.08),
    ("USA", 0.10, 0.14),
    ("Nationality", 0.10, 0.20),
    ("USA", 0.10, 0.24),
    ("Surname", 0.10, 0.30),
    ("TRAVELER", 0.10, 0.34),
    ("Given Names", 0.10, 0.40),
    ("HAPPY", 0.10, 0.44),
    ("Passport Card no.", 0.10, 0.50),
    ("C03004786", 0.10, 0.54),
    ("Sex", 0.10, 0.60),
    ("F", 0.10, 0.64),
    ("Date of Birth", 0.10, 0.70),
    ("1 JAN 1981", 0.10, 0.74),
    ("Place of Birth", 0.55, 0.70),
    ("NEW YORK, U.S.A.", 0.55, 0.74),
]


def _lines() -> list[OCRLine]:
    return [
        OCRLine(text, 0.95, (x, y, 0.30, 0.03), box_valid=True)
        for text, x, y in _CARD
    ]


def _parsed() -> dict[str, str]:
    return {
        "Type": "Passport",
        "Document Number": "C03004786",
        "Surname / Family Name": "TRAVELER",
        "Given Names": "HAPPY",
        "Nationality": "USA",
        "Date of Birth": "1 JAN 1981",
        "Sex": "F",
        "Place of Birth": "NEW YORK, U.S.A.",
        "Issued On": "undefined",
    }


def test_passport_card_fields_land_on_their_printed_lines() -> None:
    lines = _lines()
    positions = locate_field_positions(_parsed(), lines, include_boxes=True)

    assert positions["Nationality"].line_indices == [3, 4]
    assert positions["Nationality"].box_valid is True
    assert positions["Nationality"].box.y == 0.20

    assert positions["Surname / Family Name"].line_indices == [5, 6]
    assert positions["Document Number"].line_indices == [10]
    assert positions["Sex"].line_indices == [11, 12]
    assert positions["Date of Birth"].line_indices == [13, 14]
    assert positions["Place of Birth"].line_indices == [15, 16]
    assert positions["Type"].line_indices == [1]
    assert positions["Given Names"].line_indices == [7, 8]
    assert positions["Issued On"].box_valid is False
    assert positions["Issued On"].box is None

    sex = positions["Sex"].box
    assert sex.x == 0.1
    assert sex.y == 0.6
    assert sex.h == 0.07


def test_invalid_box_is_not_drawable() -> None:
    lines = [OCRLine("TRAVELER", 0.4, (0.0, 0.0, 0.0, 0.0), box_valid=False)]
    positions = locate_field_positions(
        {"Surname / Family Name": "TRAVELER"},
        lines,
        include_boxes=True,
    )
    assert positions["Surname / Family Name"].line_indices == [0]
    assert positions["Surname / Family Name"].box_valid is False
    assert positions["Surname / Family Name"].box is None


def test_short_value_does_not_match_inside_another_word() -> None:
    lines = [OCRLine("FEMALE", 0.9, (0.1, 0.1, 0.2, 0.03))]
    positions = locate_field_positions({"Sex": "F"}, lines, include_boxes=True)
    assert positions["Sex"].line_indices == []
    assert positions["Sex"].box_valid is False


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_extract_and_parse_returns_positions(monkeypatch) -> None:
    lines = _lines()
    extraction = OCRService.OCRExtraction(
        text_lines=[line.text for line in lines],
        confidences=[0.95],
        avg_confidence=0.95,
        min_confidence=0.95,
        image_width_px=800,
        image_height_px=500,
        image_rotation_degrees=0,
        blur_variance=None,
        brightness_mean=None,
        contrast_std=None,
        lines=lines,
        original_width_px=800,
        original_height_px=500,
    )
    monkeypatch.setattr(routes.ocr_service, "extract", lambda _image: extraction)
    monkeypatch.setattr(routes.parsing_service, "parse_text", lambda _text: _parsed())

    response = client.post(
        "/api/v1/extract-and-parse",
        files={"file": ("card.png", _png(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert [line["text"] for line in body["lines"]] == body["text_lines"]
    assert body["field_positions"]["Document Number"]["box_valid"] is True
    assert body["field_positions"]["Document Number"]["box"]["y"] == 0.54
    assert body["field_positions"]["Nationality"]["line_indices"] == [3, 4]
    assert body["image"] == {"original_width_px": 800, "original_height_px": 500}
