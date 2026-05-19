"""Unit tests for prompt generation."""
import pytest
from app.ai.prompts import (
    get_system_prompt,
    get_user_prompt,
    format_patient_context,
    format_lab_results,
    build_lab_interpretation_prompt,
)
from tests.fixtures.sample_data import (
    SAMPLE_PATIENT_CONTEXT,
    SAMPLE_LAB_ABNORMAL,
    SAMPLE_HISTORICAL,
)


class TestPromptGeneration:
    """Test prompt generation functions."""

    def test_system_prompt_exists(self):
        """Test that system prompt is generated."""
        prompt = get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "interpretation" in prompt.lower() or "lab" in prompt.lower()
        assert "JSON" in prompt

    def test_format_patient_context_none(self):
        """Test formatting when no patient context."""
        formatted = format_patient_context(None)
        assert "None provided" in formatted or formatted == "None provided."

    def test_format_patient_context_full(self):
        """Test formatting full patient context."""
        ctx = SAMPLE_PATIENT_CONTEXT.model_dump()
        formatted = format_patient_context(ctx)
        assert "P-1001" in formatted
        assert "58" in formatted
        assert "male" in formatted
        assert "Diabetes" in formatted or "Hypertension" in formatted
        assert "Metformin" in formatted

    def test_format_lab_results_empty(self):
        """Test formatting empty lab results."""
        formatted = format_lab_results([], "Current labs")
        assert "None provided" in formatted or "Current labs" in formatted

    def test_format_lab_results_with_data(self):
        """Test formatting lab results."""
        labs = [lab.model_dump() for lab in SAMPLE_LAB_ABNORMAL]
        formatted = format_lab_results(labs, "Current lab results")
        assert "WBC" in formatted
        assert "18.2" in formatted
        assert "CRP" in formatted
        assert "145" in formatted

    def test_format_lab_results_with_historical(self):
        """Test formatting historical lab results."""
        hist = [h.model_dump() for h in SAMPLE_HISTORICAL]
        formatted = format_lab_results(hist, "Historical lab results")
        assert "Creatinine" in formatted
        assert "1.0" in formatted
        assert "1.8" in formatted

    def test_get_user_prompt_structure(self):
        """Test user prompt structure."""
        ctx = SAMPLE_PATIENT_CONTEXT.model_dump()
        labs = [l.model_dump() for l in SAMPLE_LAB_ABNORMAL]
        hist = [h.model_dump() for h in SAMPLE_HISTORICAL]
        prompt = get_user_prompt(ctx, labs, hist)
        assert isinstance(prompt, str)
        assert "PATIENT CONTEXT" in prompt or "patient" in prompt.lower()
        assert "WBC" in prompt
        assert "Creatinine" in prompt
        assert "JSON" in prompt or "json" in prompt.lower()

    def test_build_lab_interpretation_prompt_structure(self):
        """Test complete prompt structure."""
        ctx = SAMPLE_PATIENT_CONTEXT.model_dump()
        labs = [l.model_dump() for l in SAMPLE_LAB_ABNORMAL]
        hist = []
        messages = build_lab_interpretation_prompt(ctx, labs, hist)
        assert isinstance(messages, list)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "content" in messages[0]
        assert "content" in messages[1]

    def test_prompt_includes_all_data(self):
        """Test that prompt includes lab and patient data."""
        ctx = SAMPLE_PATIENT_CONTEXT.model_dump()
        labs = [l.model_dump() for l in SAMPLE_LAB_ABNORMAL]
        hist = [h.model_dump() for h in SAMPLE_HISTORICAL]
        prompt = get_user_prompt(ctx, labs, hist)
        assert "18.2" in prompt
        assert "CRP" in prompt
        assert "Creatinine" in prompt
        assert "Diabetes" in prompt or "Hypertension" in prompt
