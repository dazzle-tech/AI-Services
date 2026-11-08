"""extract-and-parse returns text and structured fields, without line boxes."""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.api import routes
from app.services.ocr_service import OCRLine, OCRService
from main import app

client = TestClient(app)


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_extract_and_parse_omits_line_boxes(monkeypatch) -> None:
    lines = [OCRLine("TRAVELER", 0.95, (0.1, 0.2, 0.3, 0.04))]
    extraction = OCRService.OCRExtraction(
        text_lines=["TRAVELER"],
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
    monkeypatch.setattr(
        routes.parsing_service,
        "parse_text",
        lambda _text: {"Surname / Family Name": "TRAVELER"},
    )

    response = client.post(
        "/api/v1/extract-and-parse",
        files={"file": ("card.png", _png(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    for key in ("lines", "field_positions", "image"):
        assert key not in body
    assert body["text_lines"] == ["TRAVELER"]
    assert body["structured_data"]["Surname / Family Name"] == "TRAVELER"
    assert set(body) == {"text_lines", "structured_data", "model"}
