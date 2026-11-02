"""Box geometry, EXIF orientation, and line alignment. The vision client is not called."""

from __future__ import annotations

from io import BytesIO

import cv2
import numpy as np
import pytest
from PIL import Image, ImageOps

from app.core.config import settings
from app.services.ocr_service import OCRLine, OCRService, assess_box, lines_from_vision_payload, map_polygon_to_upright


def test_map_polygon_round_trip_and_stays_inside_unit_square() -> None:
    height, width = 50, 80
    image = np.zeros((height, width, 3), dtype=np.uint8)
    pixels = [(5, 7), (70, 10), (8, 40), (60, 33)]
    rotations = {
        0: None,
        90: cv2.ROTATE_90_CLOCKWISE,
        180: cv2.ROTATE_180,
        270: cv2.ROTATE_90_COUNTERCLOCKWISE,
    }
    for degrees, code in rotations.items():
        marked = image.copy()
        for x, y in pixels:
            marked[y, x] = (255, 0, 0)
        rotated = marked if code is None else cv2.rotate(marked, code)
        rotated_height, rotated_width = rotated.shape[:2]
        ys, xs = np.where(
            (rotated[:, :, 0] == 255) & (rotated[:, :, 1] == 0) & (rotated[:, :, 2] == 0)
        )
        found = [((int(px) + 0.5) / rotated_width, (int(py) + 0.5) / rotated_height) for py, px in zip(ys, xs)]
        mapped = map_polygon_to_upright(found, degrees)
        expected = [((x + 0.5) / width, (y + 0.5) / height) for x, y in pixels]
        assert len(mapped) == len(expected)
        for mx, my in mapped:
            assert 0.0 <= mx <= 1.0
            assert 0.0 <= my <= 1.0
            assert any(abs(mx - ex) < 1e-6 and abs(my - ey) < 1e-6 for ex, ey in expected)

    outside = map_polygon_to_upright([(-0.2, 1.4), (1.2, -0.1)], 0)
    for x, y in outside:
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0


def test_vision_payload_keeps_boxes_aligned_with_text() -> None:
    lines = lines_from_vision_payload(
        {
            "lines": [
                {"text": "Hello", "confidence": 0.91, "box": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05}},
                {"text": "   ", "confidence": 0.4, "box": {"x": 0.0, "y": 0.0, "w": 0.1, "h": 0.1}},
                {"text": "World", "confidence": None, "box": [0.0, 0.5, 0.4, 0.1]},
                {"text": "Wide", "confidence": 150, "box": {"x": -0.2, "y": 1.4, "w": 2.0, "h": 0.2}},
            ]
        }
    )
    assert [line.text for line in lines] == ["Hello", "World", "Wide"]
    assert lines[1].confidence is None
    assert lines[0].box == pytest.approx((0.1, 0.2, 0.3, 0.05))
    assert lines[0].box_valid is True
    assert lines[2].box == (0.0, 0.0, 0.0, 0.0)
    assert lines[2].box_valid is False
    assert lines[2].confidence == 1.0
    for line in lines:
        x, y, w, h = line.box
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
        assert 0.0 <= w <= 1.0 and 0.0 <= h <= 1.0
        assert x + w <= 1.0 + 1e-9
        assert y + h <= 1.0 + 1e-9


def test_box_validity_rules() -> None:
    valid, ok = assess_box({"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05})
    assert ok is True
    assert valid == pytest.approx((0.1, 0.2, 0.3, 0.05))

    missing, ok = assess_box({"x": "nope", "y": 0.1, "w": 0.2, "h": 0.05})
    assert ok is False and missing == (0.0, 0.0, 0.0, 0.0)

    absent, ok = assess_box(None)
    assert ok is False and absent == (0.0, 0.0, 0.0, 0.0)

    zero, ok = assess_box({"x": 0.1, "y": 0.1, "w": 0.0, "h": 0.1})
    assert ok is False and zero == (0.0, 0.0, 0.0, 0.0)

    outside, ok = assess_box({"x": -0.01, "y": 0.1, "w": 0.2, "h": 0.05})
    assert ok is False and outside == (0.0, 0.0, 0.0, 0.0)

    tall, ok = assess_box({"x": 0.1, "y": 0.1, "w": 0.4, "h": 0.26})
    assert ok is False and tall == (0.0, 0.0, 0.0, 0.0)

    huge, ok = assess_box({"x": 0.0, "y": 0.0, "w": 0.9, "h": 0.7})
    assert ok is False and huge == (0.0, 0.0, 0.0, 0.0)

    overshoot, ok = assess_box({"x": 0.0, "y": 0.1, "w": 1.03, "h": 0.05})
    assert ok is False and overshoot == (0.0, 0.0, 0.0, 0.0)

    clamped, ok = assess_box({"x": 0.0, "y": 0.1, "w": 1.01, "h": 0.05})
    assert ok is True
    assert clamped == pytest.approx((0.0, 0.1, 1.0, 0.05))


def _image_bytes(fmt: str, orientation: int) -> bytes:
    image = Image.new("RGB", (40, 20), (10, 20, 30))
    exif = image.getexif()
    exif[0x0112] = orientation
    buffer = BytesIO()
    image.save(buffer, format=fmt, exif=exif.tobytes())
    return buffer.getvalue()


@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
@pytest.mark.parametrize("orientation", [6, 8])
def test_exif_orientation_reports_upright_size(monkeypatch: pytest.MonkeyPatch, fmt: str, orientation: int) -> None:
    calls: list[tuple[int, int]] = []

    def _fake_run(self, rgb_image):
        height, width = rgb_image.shape[:2]
        calls.append((width, height))
        return OCRService.OCRExtraction(
            text_lines=["X"],
            confidences=[0.9],
            avg_confidence=0.9,
            min_confidence=0.9,
            image_width_px=width,
            image_height_px=height,
            image_rotation_degrees=0,
            blur_variance=100.0,
            brightness_mean=100.0,
            contrast_std=40.0,
            lines=[OCRLine("X", 0.9, (0.1, 0.1, 0.2, 0.2))],
        )

    monkeypatch.setattr(OCRService, "_recognize", _fake_run)
    monkeypatch.setattr(settings, "ocr_preprocess", False)
    monkeypatch.setattr(settings, "ocr_try_rotations_on_low_quality", False)

    payload = _image_bytes(fmt, orientation)
    stored = Image.open(BytesIO(payload))
    upright = ImageOps.exif_transpose(stored)
    assert upright is not None
    assert upright.size != stored.size

    result = OCRService().extract(payload)
    assert (result.original_width_px, result.original_height_px) == upright.size
    assert calls[0] == upright.size
