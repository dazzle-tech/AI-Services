"""End-to-end pipeline integration test."""

import io
import wave
from importlib import reload

import pytest
from fastapi.testclient import TestClient

import app.core.config as config_module
from app.db.session import init_db, reset_engine


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
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./convoscribe_integration_test.db")
    reload(config_module)
    reset_engine()
    from app.db.models import Base
    from app.db.session import get_engine

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    init_db()
    import main as main_module
    reload(main_module)
    yield TestClient(main_module.app)


def test_analyze_audio_json(client, auth_headers):
    import base64

    audio_bytes = _make_silent_wav()
    payload = {
        "audio_base64": base64.b64encode(audio_bytes).decode(),
        "filename": "visit.wav",
        "context_type": "appointment",
        "attendees": ["doctor", "nurse", "patient", "patient_companion"],
        "purpose": "soap_note",
        "detail_level": "standard",
    }
    response = client.post("/api/v1/analyze", json=payload, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["raw_transcript"]["segments"]) > 0
    assert body["role_map"] is not None
    assert body["summary"] is not None
    assert "subjective" in body["summary"]


def test_analyze_audio_sync(client, auth_headers):
    audio_bytes = _make_silent_wav()
    files = {"audio": ("visit.wav", audio_bytes, "audio/wav")}

    response = client.post("/api/v1/analyze", files=files, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["raw_transcript"]["segments"]) > 0
    assert body["role_map"] is not None
    assert body["summary"] is not None
    assert "subjective" in body["summary"]
    assert body["needs_review"] is False


def test_analyze_low_confidence_needs_review(client, auth_headers, monkeypatch):
    from app.models.schemas import RoleIdentificationResult

    def _force_low(segments, client=None, prompt_options=None):
        return RoleIdentificationResult(
            role_map={"SPEAKER_00": "patient", "SPEAKER_01": "doctor"},
            confidence="low",
            reasoning="Ambiguous",
        )

    monkeypatch.setattr("app.services.pipeline_service.identify_roles", _force_low)

    audio_bytes = _make_silent_wav()
    files = {"audio": ("visit.wav", audio_bytes, "audio/wav")}
    response = client.post("/api/v1/analyze", files=files, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["needs_review"] is True
    assert body["summary"] is None


def test_analyze_does_not_require_api_key(client, auth_headers):
    audio_bytes = _make_silent_wav()
    files = {"audio": ("visit.wav", audio_bytes, "audio/wav")}
    assert "X-API-Key" not in auth_headers
    response = client.post("/api/v1/analyze", files=files, headers=auth_headers)
    assert response.status_code == 200


def test_removed_session_endpoints_return_404(client, auth_headers):
    audio_bytes = _make_silent_wav()
    files = {"audio": ("visit.wav", audio_bytes, "audio/wav")}
    assert client.post("/api/v1/sessions", files=files, data={"patient_id": "p1"}, headers=auth_headers).status_code == 404
    assert client.get("/api/v1/health").status_code == 404
    assert client.get("/").status_code == 404
