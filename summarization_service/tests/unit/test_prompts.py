"""Unit tests for prompt generation."""
import pytest
from app.ai.prompts import (
    get_system_prompt,
    get_user_prompt,
    format_patient_data,
    build_summary_prompt
)
from tests.fixtures.sample_data import SAMPLE_PATIENT_MINIMAL, SAMPLE_PATIENT_COMPLETE


class TestPromptGeneration:
    """Test prompt generation functions."""
    
    def test_system_prompt_exists(self):
        """Test that system prompt is generated."""
        prompt = get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "medical" in prompt.lower() or "clinical" in prompt.lower()
    
    def test_format_patient_data_minimal(self):
        """Test formatting minimal patient data."""
        patient_dict = SAMPLE_PATIENT_MINIMAL.dict()
        formatted = format_patient_data(patient_dict)
        
        assert "45 years" in formatted
        assert "Male" in formatted
        assert "Type 2 Diabetes" in formatted
    
    def test_format_patient_data_complete(self):
        """Test formatting complete patient data."""
        patient_dict = SAMPLE_PATIENT_COMPLETE.dict()
        formatted = format_patient_data(patient_dict)
        
        assert "58 years" in formatted
        assert "STEMI" in formatted
        assert "Chest pain" in formatted or "chest pain" in formatted.lower()
        assert "Aspirin" in formatted
        assert "Penicillin" in formatted
        assert "140/90" in formatted
    
    def test_format_patient_data_with_vitals(self):
        """Test formatting patient data with vitals."""
        patient_dict = {
            "Age": "45 years",
            "Gender": "Male",
            "Diagnosis": "Diabetes",
            "Vitals": {"BP": "120/80", "HR": "72"}
        }
        formatted = format_patient_data(patient_dict)
        
        assert "BP 120/80" in formatted or "120/80" in formatted
        assert "HR 72" in formatted or "72" in formatted
    
    def test_get_user_prompt_structure(self):
        """Test user prompt structure."""
        patient_dict = SAMPLE_PATIENT_MINIMAL.dict()
        prompt = get_user_prompt(patient_dict)
        
        assert isinstance(prompt, str)
        assert "PATIENT DATA" in prompt or "Patient data" in prompt
        assert "45 years" in prompt
    
    def test_build_summary_prompt_structure(self):
        """Test complete prompt structure."""
        patient_dict = SAMPLE_PATIENT_MINIMAL.dict()
        messages = build_summary_prompt(patient_dict)
        
        assert isinstance(messages, list)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "content" in messages[0]
        assert "content" in messages[1]
    
    def test_prompt_includes_all_data(self):
        """Test that prompt includes all patient data fields."""
        patient_dict = SAMPLE_PATIENT_COMPLETE.dict()
        prompt = get_user_prompt(patient_dict)
        
        # Check that all major fields are represented
        assert "58 years" in prompt
        assert "STEMI" in prompt or "Myocardial" in prompt
        assert "Aspirin" in prompt or "aspirin" in prompt.lower()
        assert "Penicillin" in prompt or "penicillin" in prompt.lower()

