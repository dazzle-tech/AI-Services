"""Pytest configuration: everything runs on the stub (no speech API, no API key)."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import reload_settings
from main import app


@pytest.fixture(autouse=True)
def test_env(monkeypatch):
    monkeypatch.setenv("USE_LLM_STUB", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    # Tests send audio much faster than real time; do not treat that as a backlog.
    monkeypatch.setenv("MAX_BACKLOG_SECONDS", "1000")
    monkeypatch.setenv("PICKED_UP_INTERVAL_SECONDS", "8")
    reload_settings()
    yield
    monkeypatch.undo()
    reload_settings()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
