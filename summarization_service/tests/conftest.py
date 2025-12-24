"""Pytest configuration and shared fixtures."""
import pytest
import os
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-for-testing-only")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0.2")


@pytest.fixture
def sample_patient_data():
    """Sample patient data for testing."""
    return {
        "Age": "45 years",
        "Gender": "Male",
        "Diagnosis": "Type 2 Diabetes",
        "Symptoms": ["Polyuria", "Polydipsia"],
        "Medications": ["Metformin 500mg BID"],
        "Allergies": ["Penicillin"]
    }

