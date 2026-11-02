"""Provider and parse errors stay generic. The OpenAI client is mocked."""

from __future__ import annotations

from io import BytesIO

import httpx
from fastapi.testclient import TestClient
from openai import APITimeoutError, AuthenticationError
from PIL import Image

from app.api import routes
from main import app

client = TestClient(app)


def _png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def _post_identity() -> object:
    return client.post(
        "/api/v1/identity/extract",
        files={"file": ("id.png", _png(), "image/png")},
    )


def test_missing_api_key_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(routes.identity_service.ocr._client, "api_key", "")
    response = _post_identity()
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "OCR_UNAVAILABLE",
        "message": "The reading service is temporarily unavailable.",
    }
    assert "api_key" not in response.text.lower()
    assert "sk-" not in response.text


def test_auth_error_hides_provider_text(monkeypatch) -> None:
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    response_obj = httpx.Response(401, request=request)

    def _boom(*_args, **_kwargs):
        raise AuthenticationError("sk-live-secret", response=response_obj, body={"error": "sk-live-secret"})

    monkeypatch.setattr(routes.identity_service.ocr._client, "generate_vision_json", _boom)
    response = _post_identity()
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "OCR_UNAVAILABLE"
    assert "sk-live-secret" not in response.text
    assert "base64" not in response.text


def test_timeout_is_unavailable(monkeypatch) -> None:
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")

    def _boom(*_args, **_kwargs):
        raise APITimeoutError(request)

    monkeypatch.setattr(routes.identity_service.ocr._client, "generate_vision_json", _boom)
    response = _post_identity()
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "OCR_UNAVAILABLE"
    assert "example.test" not in response.text


def test_extract_text_error_is_generic(monkeypatch) -> None:
    def _boom(_image_bytes: bytes):
        raise RuntimeError("PASSPORT LINE SECRET")

    monkeypatch.setattr(routes.ocr_service, "extract", _boom)
    response = client.post(
        "/api/v1/extract-text",
        files={"file": ("id.png", _png(), "image/png")},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "OCR extraction failed"
    assert "SECRET" not in response.text


def test_parse_error_is_generic(monkeypatch) -> None:
    def _boom(_text: str):
        raise RuntimeError("recognized line stays server side")

    monkeypatch.setattr(routes.parsing_service, "parse_text", _boom)
    response = client.post("/api/v1/parse-text", json={"text": "hello"})
    assert response.status_code == 500
    assert response.json()["detail"] == "Parsing failed"
    assert "recognized line" not in response.text


def test_parse_value_error_is_generic(monkeypatch) -> None:
    def _boom(_text: str):
        raise ValueError("model said NAME DOE")

    monkeypatch.setattr(routes.parsing_service, "parse_text", _boom)
    response = client.post("/api/v1/parse-text", json={"text": "hello"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Parsing failed"
    assert "NAME DOE" not in response.text


def test_extract_and_parse_error_is_generic(monkeypatch) -> None:
    def _boom(_image_bytes: bytes):
        raise RuntimeError("image bytes and text")

    monkeypatch.setattr(routes.ocr_service, "extract", _boom)
    response = client.post(
        "/api/v1/extract-and-parse",
        files={"file": ("id.png", _png(), "image/png")},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Extract-and-parse failed"
    assert "image bytes" not in response.text
