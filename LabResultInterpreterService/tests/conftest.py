"""Pytest configuration and shared fixtures."""
import os

# Set env vars before any app imports (during collection)
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-testing-only")
os.environ.setdefault("OPENAI_MODEL", "")
os.environ.setdefault("OPENAI_TEMPERATURE", "0.2")

import pytest


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing (reinforce for test runs)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-for-testing-only")
    monkeypatch.setenv("OPENAI_MODEL", os.getenv("OPENAI_MODEL", ""))
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0.2")


@pytest.fixture
def sample_lab_data():
    """Sample lab data for testing."""
    return {
        "lab_results": [
            {
                "name": "WBC",
                "value": "18.2",
                "unit": "10^9/L",
                "reference_range": "4.0-11.0",
                "flag": "high",
                "timestamp": "2026-03-16T08:00:00Z",
            }
        ],
        "historical_lab_results": [],
    }
