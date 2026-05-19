"""Unit tests for prompt generation."""
from app.ai.prompts import (
    build_alert_prompt,
    format_patient_record,
    format_risk_signals,
    get_system_prompt,
    get_user_prompt,
)
from tests.fixtures.sample_data import SAMPLE_PATIENT_COMPLETE, SAMPLE_PATIENT_MINIMAL


class TestPromptGeneration:
    """Test prompt generation functions."""

    def test_system_prompt_exists(self):
        """Test that system prompt is generated."""
        prompt = get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "clinical decision support" in prompt.lower()
        assert "return only a json array" in prompt.lower()

    def test_format_patient_record_minimal(self):
        """Test formatting minimal patient record."""
        patient_dict = SAMPLE_PATIENT_MINIMAL.model_dump()
        formatted = format_patient_record(patient_dict)

        assert "P-1001" in formatted
        assert "58" in formatted
        assert "male" in formatted

    def test_format_patient_record_complete(self):
        """Test formatting complete patient record."""
        patient_dict = SAMPLE_PATIENT_COMPLETE.model_dump()
        formatted = format_patient_record(patient_dict)

        assert "Troponin" in formatted
        assert "Creatinine" in formatted
        assert "Ibuprofen" in formatted
        assert "intracranial hemorrhage" in formatted

    def test_get_user_prompt_structure(self):
        """Test user prompt structure."""
        patient_dict = SAMPLE_PATIENT_MINIMAL.model_dump()
        prompt = get_user_prompt(
            patient_dict,
            risk_signals=[{"summary": "Example risk signal", "evidence": ["Lab Creatinine 1.8 mg/dL"]}],
        )

        assert isinstance(prompt, str)
        assert "PATIENT RECORD" in prompt
        assert "DETERMINISTIC RISK SIGNAL SUMMARY" in prompt
        assert "JSON array" in prompt
        assert "P-1001" in prompt

    def test_format_risk_signals(self):
        """Test deterministic risk signal formatting."""
        formatted = format_risk_signals(
            [{"summary": "Creatinine trend", "evidence": ["Lab Creatinine 1.8 mg/dL on 2026-03-16"]}]
        )
        assert "Creatinine trend" in formatted
        assert "2026-03-16" in formatted

    def test_build_alert_prompt_structure(self):
        """Test complete prompt structure."""
        patient_dict = SAMPLE_PATIENT_MINIMAL.model_dump()
        messages = build_alert_prompt(patient_dict, risk_signals=[{"summary": "Example"}])

        assert isinstance(messages, list)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "content" in messages[0]
        assert "content" in messages[1]

    def test_prompt_includes_alert_requirements(self):
        """Test prompt includes safety and output requirements."""
        patient_dict = SAMPLE_PATIENT_COMPLETE.model_dump()
        prompt = get_user_prompt(patient_dict)
        system_prompt = get_system_prompt()

        assert "supporting_evidence" in system_prompt
        assert "never invent" in system_prompt.lower()
        assert "rank alerts from most severe to least severe" in prompt.lower()
        assert "deterministic risk signal summary" in get_user_prompt(patient_dict).lower()
