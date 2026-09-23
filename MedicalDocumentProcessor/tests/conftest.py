"""Pytest configuration and shared fixtures."""
import os

# Set env vars before any app imports (during collection)
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-testing-only")
os.environ.setdefault("OPENAI_MODEL", "gpt-4o")
os.environ.setdefault("OPENAI_TEMPERATURE", "0.1")

import pytest


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing (reinforce for test runs)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-for-testing-only")
    monkeypatch.setenv("OPENAI_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o"))
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0.1")
