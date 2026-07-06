"""Pytest configuration and shared fixtures."""
import os
import pytest


def pytest_configure(config):
    """Set env vars before any modules are imported (e.g. config loading)."""
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-testing-only")
    os.environ.setdefault("OPENAI_MODEL", "")
    os.environ.setdefault("OPENAI_TEMPERATURE", "0.2")


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-for-testing-only")
    monkeypatch.setenv("OPENAI_MODEL", os.getenv("OPENAI_MODEL", ""))
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0.2")
