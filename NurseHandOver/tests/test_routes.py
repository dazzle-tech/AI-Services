"""API tests — generate must succeed with no request headers."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.schemas import GenerateSummaryResponse, PatientSummaryResult
from main import app

MINIMAL_BODY = {
    "shift_id": "shift-minimal",
    "nurse_id": "nurse_001",
    "patients": [{"patient_id": "pt_min", "name": "Alex Rivera"}],
}


@pytest.fixture
def client():
    return TestClient(app)


def _fake_response():
    stamp = datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
    return GenerateSummaryResponse(
        shift_id="shift-minimal",
        status="draft",
        generated_at=stamp,
        results=[
            PatientSummaryResult(patient_id="pt_min", success=True, summary=None, error=None),
        ],
    )


def test_generate_without_any_headers(client):
    with patch(
        "app.routes.summary.generate_shift_summaries",
        new=AsyncMock(return_value=_fake_response()),
    ):
        response = client.post(
            "/summary/generate",
            content=json.dumps(MINIMAL_BODY),
            headers={},
        )
    assert response.status_code == 200
    assert response.json()["shift_id"] == "shift-minimal"


def test_health_without_headers(client):
    response = client.get("/health", headers={})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
