"""Pytest configuration and shared fixtures."""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-testing-only")
os.environ.setdefault("OPENAI_MODEL", "gpt-4o")
os.environ.setdefault("OPENAI_TEMPERATURE", "0.2")
os.environ.setdefault("API_PORT", "8001")
os.environ.setdefault("LOG_LEVEL", "INFO")


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-for-testing-only")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0.2")
    monkeypatch.setenv("API_PORT", "8001")
    monkeypatch.setenv("LOG_LEVEL", "INFO")


@pytest.fixture
def sample_patient_data():
    """Sample patient data for testing."""
    return {
        "patient_id": "12345",
        "demographics": {
            "age": "58 years",
            "gender": "Male"
        },
        "diagnoses": [
            {
                "name": "Type 2 Diabetes",
                "date": "2022-05-01"
            }
        ]
    }
