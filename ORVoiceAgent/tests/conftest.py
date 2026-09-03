"""Pytest configuration."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import reload_settings
from main import app


@pytest.fixture(autouse=True)
def test_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("ORSCRIBE_API_KEY", "test-api-key")
    monkeypatch.setenv("ORSCRIBE_BASE_URL", "http://localhost:8030")
    monkeypatch.setenv("ORDISPLAY_BASE_URL", "http://localhost:8032")
    reload_settings()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
