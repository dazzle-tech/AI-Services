"""Pytest configuration and shared fixtures."""
import os

import pytest


os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-for-testing-only")
os.environ.setdefault("OPENAI_MODEL", "")
os.environ.setdefault("OPENAI_TEMPERATURE", "0.1")
os.environ.setdefault("API_PORT", "8005")
os.environ.setdefault("LOG_LEVEL", "INFO")


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-for-testing-only")
    monkeypatch.setenv("OPENAI_MODEL", os.getenv("OPENAI_MODEL", ""))
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0.1")
    monkeypatch.setenv("API_PORT", "8005")
    monkeypatch.setenv("LOG_LEVEL", "INFO")


@pytest.fixture
def sample_patient_record():
    """Sample patient record for testing."""
    return {
        "patient_id": "P-1001",
        "demographics": {"age": 58, "sex": "male"},
        "diagnoses": [{"name": "Type 2 Diabetes", "date": "2022-05-01"}],
        "lab_results": [
            {
                "name": "Creatinine",
                "value": "1.8",
                "unit": "mg/dL",
                "reference_range": "0.7-1.3",
                "flag": "high",
                "date": "2026-03-16",
            }
        ],
        "notes": [
            {
                "date": "2026-03-16",
                "author": "Dr. Lee",
                "type": "progress_note",
                "text": "Renal function worsened since admission.",
            }
        ],
    }
