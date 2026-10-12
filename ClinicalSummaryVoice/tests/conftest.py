"""Pytest configuration."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import reload_settings
from main import app


@pytest.fixture(autouse=True)
def test_env(monkeypatch):
    monkeypatch.setenv("USE_LLM_STUB", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    reload_settings()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
