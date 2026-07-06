"""Pytest configuration and shared fixtures."""
import pytest
import os
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-for-testing-only")
    monkeypatch.setenv("OPENAI_MODEL", os.getenv("OPENAI_MODEL", ""))
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0.2")


@pytest.fixture
def sample_discharge_input():
    """Sample discharge planning input for testing."""
    return {
        "patient_context": {
            "patient_id": "P-1001",
            "admission_date": "2026-03-10",
            "primary_diagnosis": "Pneumonia",
            "secondary_diagnoses": ["Type 2 Diabetes", "Hypertension"],
            "current_status": "improving",
        },
        "clinical_data": {
            "latest_vitals": [{"name": "temperature", "value": "37.1", "unit": "C"}],
            "pending_tests": [{"name": "blood culture", "status": "pending"}],
            "active_problems": ["Needs home oxygen assessment"],
            "medications_current": ["Amoxicillin", "Metformin"],
            "medications_planned_for_discharge": ["Amoxicillin", "Metformin", "Prednisone"],
        },
        "operational_data": {
            "follow_up_appointments": [{"service": "Pulmonology", "scheduled": False}],
            "patient_education": [
                {"topic": "antibiotic adherence", "completed": True},
                {"topic": "warning signs and return precautions", "completed": False},
            ],
            "transport_status": "available",
            "home_support": "family_available",
        },
    }
