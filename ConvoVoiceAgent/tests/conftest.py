"""Pytest configuration."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import reload_settings
from main import app


@pytest.fixture(autouse=True)
def test_env(monkeypatch):
    monkeypatch.setenv("CONVOSCRIBE_BASE_URL", "http://localhost:8026")
    monkeypatch.setenv("SYSTEM_DISPLAY_BASE_URL", "http://localhost:8031")
    monkeypatch.setenv("DEFAULT_VIEW_IDS", "soap_note")
    reload_settings()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
