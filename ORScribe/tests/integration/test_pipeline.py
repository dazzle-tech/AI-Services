"""End-to-end pipeline integration test."""

import io
import wave
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import reload_settings
from app.db.models import CaseStatus
from app.db.session import init_db, reset_engine
from app.jobs.tasks import process_analysis_pipeline, process_audio_chunk
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


class InMemoryStorage:
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def upload_audio(self, case_id, filename, data, content_type):
        uri = f"s3://test-bucket/cases/{case_id}/{filename}"
        self._objects[uri] = data
        return uri

    def download_audio(self, audio_uri: str) -> bytes:
        return self._objects[audio_uri]

    def delete_audio(self, audio_uri: str) -> None:
        self._objects.pop(audio_uri, None)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./orscribe_integration_test.db")
    reload_settings()
    reset_engine()
    from app.db.models import Base
    from app.db.session import get_engine

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    init_db()
    storage = InMemoryStorage()

    def _run_chunk(case_id: str, chunk_id: str):
        process_audio_chunk.run(case_id, chunk_id)

    def _run_analysis(case_id: str, start_at: str = "roles"):
        process_analysis_pipeline.run(case_id, start_at)

    with patch("app.services.case_service.process_audio_chunk") as mock_chunk, patch(
        "app.services.case_service.process_analysis_pipeline"
    ) as mock_analysis, patch(
        "app.jobs.tasks.process_analysis_pipeline"
    ) as mock_analysis_task, patch(
        "app.services.case_service.ObjectStorage", return_value=storage
    ), patch("app.jobs.tasks.ObjectStorage", return_value=storage):
        mock_chunk.delay.side_effect = _run_chunk
        mock_analysis.delay.side_effect = _run_analysis
        mock_analysis_task.delay.side_effect = _run_analysis
        yield TestClient(app)


def test_full_pipeline_end_to_end(client, auth_headers):
    audio_bytes = _make_silent_wav()
    files = {"audio": ("case.wav", audio_bytes, "audio/wav")}
    data = {"procedure_type": "laparoscopic cholecystectomy", "ingest_mode": "post_hoc"}

    create_response = client.post("/api/v1/cases", files=files, data=data, headers=auth_headers)
    assert create_response.status_code == 202
    case_id = create_response.json()["case_id"]

    detail = client.get(f"/api/v1/cases/{case_id}", headers=auth_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == CaseStatus.COMPLETED.value
    assert body["role_map"] is not None
    assert body["timeline"] is not None
    assert body["checklist_result"] is not None

    transcript = client.get(f"/api/v1/cases/{case_id}/transcript", headers=auth_headers)
    assert transcript.status_code == 200
    assert len(transcript.json()["raw_transcript"]["segments"]) > 0

    checklist = client.get(f"/api/v1/cases/{case_id}/checklist", headers=auth_headers)
    assert checklist.status_code == 200
    assert "sign_in" in checklist.json()

    approve = client.post(
        f"/api/v1/cases/{case_id}/approve",
        json={"user_id": "nurse-1"},
        headers=auth_headers,
    )
    assert approve.status_code == 200
    assert approve.json()["approved_by"] == "nurse-1"


def test_low_confidence_role_correction(client, auth_headers, monkeypatch):
    from app.models.schemas import RoleIdentificationResult, SpeakerRoleAssignment

    def _force_review(segments, scheduled_team=None, client=None, prompt_options=None):
        return RoleIdentificationResult(
            role_map={
                "SPEAKER_00": SpeakerRoleAssignment(role="unidentified", confidence="low", needs_review=True),
                "SPEAKER_01": SpeakerRoleAssignment(role="unidentified", confidence="low", needs_review=True),
            },
            reasoning="Ambiguous",
        )

    monkeypatch.setattr("app.jobs.tasks.identify_roles", _force_review)

    audio_bytes = _make_silent_wav()
    files = {"audio": ("case.wav", audio_bytes, "audio/wav")}
    data = {"procedure_type": "appendectomy"}

    create_response = client.post("/api/v1/cases", files=files, data=data, headers=auth_headers)
    case_id = create_response.json()["case_id"]

    detail = client.get(f"/api/v1/cases/{case_id}", headers=auth_headers)
    assert detail.json()["needs_review"] is True

    patch_response = client.patch(
        f"/api/v1/cases/{case_id}/roles",
        json={"role_map": {"SPEAKER_00": "surgeon", "SPEAKER_01": "anesthetist"}},
        headers=auth_headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["needs_review"] is False
    assert patch_response.json()["timeline"] is not None


def test_analyze_audio_sync(client, auth_headers):
    audio_bytes = _make_silent_wav()
    files = {"audio": ("case.wav", audio_bytes, "audio/wav")}

    response = client.post("/api/v1/analyze", files=files, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["raw_transcript"]["segments"]) > 0
    assert body["role_map"] is not None
    assert body["needs_review"] is False
    assert body["timeline"] is not None
    assert body["checklist"] is not None
    assert "sign_in" in body["checklist"]
