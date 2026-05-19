"""Unit tests for prompt generation."""
import pytest
from app.ai.prompts import (
    get_system_prompt,
    format_discharge_input,
    get_user_prompt,
    build_discharge_prompt,
)
from tests.fixtures.sample_data import SAMPLE_REQUEST_MINIMAL, SAMPLE_REQUEST_FULL


class TestPromptGeneration:
    """Test prompt generation functions."""
    
    def test_system_prompt_exists(self):
        """Test that system prompt is generated."""
        prompt = get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "discharge" in prompt.lower()
        assert "JSON" in prompt or "json" in prompt
    
    def test_system_prompt_includes_safety(self):
        """Test system prompt includes safety requirements."""
        prompt = get_system_prompt()
        assert "clinician" in prompt.lower() or "judgment" in prompt.lower()
        assert "never" in prompt.lower() or "does not replace" in prompt.lower()
    
    def test_format_discharge_input_minimal(self):
        """Test formatting minimal discharge input."""
        data = {
            "patient_context": SAMPLE_REQUEST_MINIMAL.patient_context.model_dump(),
            "clinical_data": SAMPLE_REQUEST_MINIMAL.clinical_data.model_dump(),
            "operational_data": SAMPLE_REQUEST_MINIMAL.operational_data.model_dump(),
        }
        formatted = format_discharge_input(data)
        assert "P-1001" in formatted
        assert "Pneumonia" in formatted
    
    def test_format_discharge_input_full(self):
        """Test formatting full discharge input."""
        data = {
            "patient_context": SAMPLE_REQUEST_FULL.patient_context.model_dump(),
            "clinical_data": SAMPLE_REQUEST_FULL.clinical_data.model_dump(),
            "operational_data": SAMPLE_REQUEST_FULL.operational_data.model_dump(),
        }
        formatted = format_discharge_input(data)
        assert "temperature" in formatted or "37.1" in formatted
        assert "Amoxicillin" in formatted
        assert "Pulmonology" in formatted
        assert "home oxygen" in formatted or "oxygen" in formatted.lower()
    
    def test_get_user_prompt_structure(self):
        """Test user prompt structure."""
        data = {
            "patient_context": SAMPLE_REQUEST_MINIMAL.patient_context.model_dump(),
            "clinical_data": SAMPLE_REQUEST_MINIMAL.clinical_data.model_dump(),
            "operational_data": SAMPLE_REQUEST_MINIMAL.operational_data.model_dump(),
        }
        prompt = get_user_prompt(data)
        assert isinstance(prompt, str)
        assert "PATIENT CONTEXT" in prompt or "patient" in prompt.lower()
        assert "JSON" in prompt or "json" in prompt
    
    def test_build_discharge_prompt_structure(self):
        """Test complete prompt structure."""
        data = {
            "patient_context": SAMPLE_REQUEST_MINIMAL.patient_context.model_dump(),
            "clinical_data": SAMPLE_REQUEST_MINIMAL.clinical_data.model_dump(),
            "operational_data": SAMPLE_REQUEST_MINIMAL.operational_data.model_dump(),
        }
        messages = build_discharge_prompt(data)
        assert isinstance(messages, list)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "content" in messages[0]
        assert "content" in messages[1]
