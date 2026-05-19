"""Unit tests for prompt generation."""
import pytest
from app.ai.prompts import (
    get_system_prompt,
    get_user_prompt,
    format_patient_data,
    build_prioritization_prompt
)
from tests.fixtures.sample_data import SAMPLE_PATIENT_MINIMAL, SAMPLE_PATIENT_FULL


class TestPromptGeneration:
    """Test prompt generation functions."""

    def test_system_prompt_exists(self):
        """Test that system prompt is generated."""
        prompt = get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "priorit" in prompt.lower() or "nursing" in prompt.lower()

    def test_system_prompt_requires_json(self):
        """Test that system prompt mentions JSON output."""
        prompt = get_system_prompt()
        assert "JSON" in prompt.upper()

    def test_format_patient_data_minimal(self):
        """Test formatting minimal patient data."""
        request_dict = {
            "unit_context": {"unit_name": "Ward A", "shift": "day", "generated_at": "2026-03-16T09:00:00Z"},
            "nurse_context": {"nurse_id": "N-1", "assigned_rooms": ["101"]},
            "patients": [SAMPLE_PATIENT_MINIMAL.model_dump()]
        }
        formatted = format_patient_data(request_dict)
        assert "P-1001" in formatted
        assert "101" in formatted
        assert "Ward A" in formatted or "day" in formatted

    def test_format_patient_data_full(self):
        """Test formatting complete patient data."""
        request_dict = {
            "unit_context": {"unit_name": "Medical Ward A", "shift": "day", "generated_at": "2026-03-16T09:00:00Z"},
            "nurse_context": {"nurse_id": "N-204", "assigned_rooms": ["101", "102"]},
            "patients": [SAMPLE_PATIENT_FULL.model_dump()]
        }
        formatted = format_patient_data(request_dict)
        assert "oxygen_saturation" in formatted or "88" in formatted
        assert "Insulin" in formatted
        assert "Reassess oxygen therapy" in formatted
        assert "fall_risk" in formatted
        assert "short of breath" in formatted or "ambulation" in formatted

    def test_format_patient_data_with_vitals(self):
        """Test formatting patient data with vitals."""
        request_dict = {
            "unit_context": {"unit_name": "Ward", "shift": "day", "generated_at": "2026-03-16T09:00:00Z"},
            "nurse_context": {"nurse_id": "N-1", "assigned_rooms": []},
            "patients": [{
                "patient_id": "P-1",
                "room": "101",
                "patient_risk_flags": [],
                "vitals": [{"name": "heart_rate", "value": "72", "unit": "bpm", "timestamp": "2026-03-16T08:00:00Z"}],
                "lab_alerts": [],
                "medication_tasks": [],
                "nursing_tasks": [],
                "notes": []
            }]
        }
        formatted = format_patient_data(request_dict)
        assert "heart_rate" in formatted or "72" in formatted

    def test_get_user_prompt_structure(self):
        """Test user prompt structure."""
        request_dict = {
            "unit_context": {"unit_name": "Ward", "shift": "day", "generated_at": "2026-03-16T09:00:00Z"},
            "nurse_context": {"nurse_id": "N-1", "assigned_rooms": ["101"]},
            "patients": [SAMPLE_PATIENT_MINIMAL.model_dump()]
        }
        prompt = get_user_prompt(request_dict)
        assert isinstance(prompt, str)
        assert "INPUT DATA" in prompt or "Prioritize" in prompt
        assert "P-1001" in prompt

    def test_build_prioritization_prompt_structure(self):
        """Test complete prompt structure."""
        request_dict = {
            "unit_context": {"unit_name": "Ward", "shift": "day", "generated_at": "2026-03-16T09:00:00Z"},
            "nurse_context": {"nurse_id": "N-1", "assigned_rooms": []},
            "patients": [SAMPLE_PATIENT_MINIMAL.model_dump()]
        }
        messages = build_prioritization_prompt(request_dict)
        assert isinstance(messages, list)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "content" in messages[0]
        assert "content" in messages[1]
