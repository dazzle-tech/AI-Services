"""Integration tests for POST /api/v1/windows/transcribe."""

import io
import wave

import pytest
from fastapi.testclient import TestClient

from main import app


def _make_silent_wav(duration_seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    num_frames = int(duration_seconds * sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * num_frames)
    return buffer.getvalue()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_window_transcribe_stub_backend(client):
    audio_bytes = _make_silent_wav()
    files = {"audio": ("window.wav", audio_bytes, "audio/wav")}
    data = {
        "case_id": "case-123",
        "window_id": "nursing_time_out",
        "role": "nurse",
    }
    response = client.post(
        "/api/v1/windows/transcribe",
        files=files,
        data=data,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == "case-123"
    assert body["window_id"] == "nursing_time_out"
    assert body["role"] == "nurse"
    assert body["staff_id"] == ""
    assert body["language"] == "en"
    assert body["duration_seconds"] > 0
    assert "transcribed_at" in body
    assert len(body["text"]) > 0
    assert "Time out" in body["text"]
    assert "Correct patient" in body["text"]


def test_window_transcribe_intraoperative_stub_text(client):
    audio_bytes = _make_silent_wav()
    files = {"audio": ("window.wav", audio_bytes, "audio/wav")}
    data = {
        "window_id": "nursing_intraoperative",
        "role": "nurse",
    }
    response = client.post("/api/v1/windows/transcribe", files=files, data=data)
    assert response.status_code == 200
    assert "Operation date 2026-09-03" in response.json()["text"]


def test_window_transcribe_without_staff_id(client):
    audio_bytes = _make_silent_wav()
    files = {"audio": ("window.wav", audio_bytes, "audio/wav")}
    data = {
        "case_id": "case-123",
        "window_id": "operative_note",
        "role": "surgeon",
    }
    response = client.post(
        "/api/v1/windows/transcribe",
        files=files,
        data=data,
    )
    assert response.status_code == 200
    assert response.json()["staff_id"] == ""


def test_window_transcribe_unknown_window_id(client):
    audio_bytes = _make_silent_wav()
    files = {"audio": ("window.wav", audio_bytes, "audio/wav")}
    data = {
        "case_id": "case-123",
        "window_id": "not_a_real_window",
        "role": "nurse",
    }
    response = client.post(
        "/api/v1/windows/transcribe",
        files=files,
        data=data,
    )
    assert response.status_code == 422


def test_window_transcribe_invalid_role(client):
    audio_bytes = _make_silent_wav()
    files = {"audio": ("window.wav", audio_bytes, "audio/wav")}
    data = {
        "case_id": "case-123",
        "window_id": "nursing_time_out",
        "role": "scrub_tech",
    }
    response = client.post(
        "/api/v1/windows/transcribe",
        files=files,
        data=data,
    )
    assert response.status_code == 422
