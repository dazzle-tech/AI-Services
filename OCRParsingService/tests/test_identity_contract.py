"""HTTP contract for /api/v1/identity/extract. The vision client is not called."""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import settings
from app.services.ocr_service import OCRLine, OCRService
from main import app

client = TestClient(app)

_LINES = [
    "Name: JANE DOE",
    "Date of Birth: 02/03/1990",
    "Sex: F",
    "Nationality: CANADA",
    "Passport No: AB123456",
]


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def _extraction() -> OCRService.OCRExtraction:
    confidences = [0.93, 0.91, 0.90, 0.92, 0.94]
    lines = [
        OCRLine(text, confidence, (0.08, 0.12 + index * 0.08, 0.4, 0.05))
        for index, (text, confidence) in enumerate(zip(_LINES, confidences))
    ]
    return OCRService.OCRExtraction(
        text_lines=list(_LINES),
        confidences=confidences,
        avg_confidence=sum(confidences) / len(confidences),
        min_confidence=min(confidences),
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


def _post(monkeypatch, return_boxes: bool) -> dict:
    monkeypatch.setattr(settings, "ocr_return_boxes", return_boxes)
    monkeypatch.setattr(settings, "identity_llm_fallback_enabled", False)
    from app.api import routes

    monkeypatch.setattr(routes.identity_service.ocr, "extract", lambda _image_bytes: _extraction())
    response = client.post(
        "/api/v1/identity/extract",
        files={"file": ("id.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    return response.json()


def test_identity_response_omits_positions(monkeypatch) -> None:
    body = _post(monkeypatch, True)
    assert body["text_lines"] == _LINES
    for key in ("lines", "field_sources", "image"):
        assert key not in body
    assert body["identity"]["full_name"] == "Jane Doe"
    assert body["identity"]["document_number"] == "AB123456"
    assert "quality" in body and "validation" in body
    assert "mrz_present" in body and "mrz_valid" in body
