"""Unit tests for prompt generation."""
from app.ai.prompts import (
    build_timeline_prompt,
    format_patient_data,
    get_system_prompt,
    get_user_prompt,
)
from tests.fixtures.sample_data import SAMPLE_REQUEST_COMPLETE, SAMPLE_REQUEST_MINIMAL


class TestPromptGeneration:
    """Test prompt generation functions."""

    def test_system_prompt_exists(self):
        """Test that system prompt is generated."""
        prompt = get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "json" in prompt.lower()
        assert "clinical" in prompt.lower()

    def test_format_patient_data_minimal(self):
        """Test formatting minimal patient data."""
        patient_dict = SAMPLE_REQUEST_MINIMAL.model_dump(exclude={"request_id"})
        formatted = format_patient_data(patient_dict)

        assert "58 years" in formatted
        assert "Hypertension" in formatted

    def test_format_patient_data_complete(self):
        """Test formatting complete patient data."""
        patient_dict = SAMPLE_REQUEST_COMPLETE.model_dump(exclude={"request_id"})
        formatted = format_patient_data(patient_dict)

        assert "Coronary angiography" in formatted
        assert "Troponin" in formatted
        assert "Penicillin" in formatted
        assert "admission_note" in formatted

    def test_get_user_prompt_structure(self):
        """Test user prompt structure."""
        patient_dict = SAMPLE_REQUEST_MINIMAL.model_dump(exclude={"request_id"})
        prompt = get_user_prompt(patient_dict)

        assert isinstance(prompt, str)
        assert "PATIENT DATA" in prompt
        assert "STRICT JSON" in prompt
        assert "Hypertension" in prompt

    def test_build_timeline_prompt_structure(self):
        """Test complete prompt structure."""
        patient_dict = SAMPLE_REQUEST_MINIMAL.model_dump(exclude={"request_id"})
        messages = build_timeline_prompt(patient_dict)

        assert isinstance(messages, list)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "content" in messages[0]
        assert "content" in messages[1]

    def test_prompt_includes_required_instructions(self):
        """Test that prompt includes timeline extraction instructions."""
        patient_dict = SAMPLE_REQUEST_COMPLETE.model_dump(exclude={"request_id"})
        prompt = get_user_prompt(patient_dict)

        assert "Merge duplicates" in prompt
        assert "Return only a JSON array" in prompt
