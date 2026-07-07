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

    def test_format_patient_data_with_lab_results(self):
        """Test formatting patient data with lab results."""
        patient_dict = {
            "Age": "45 years",
            "Gender": "Male",
            "Diagnosis": "Diabetes",
            "Lab_Results": {"HbA1c": "7.5%", "Creatinine": "1.1 mg/dL"}
        }
        formatted = format_patient_data(patient_dict)
        
        assert "HbA1c" in formatted or "7.5" in formatted
        assert "Creatinine" in formatted or "1.1" in formatted

    def test_format_patient_data_with_surgeries_status(self):
        """Test formatting patient data with surgeries (completed/scheduled)."""
        patient_dict = {
            "Age": "45 years",
            "Gender": "Male",
            "Diagnosis": "Diabetes",
            "Surgeries": [
                {"name": "Appendectomy 2010", "status": "completed"},
                {"name": "Knee replacement", "status": "scheduled"},
            ],
        }
        formatted = format_patient_data(patient_dict)
        
        assert "Appendectomy" in formatted or "2010" in formatted
        assert "completed" in formatted
        assert "scheduled" in formatted
        assert "Knee" in formatted or "replacement" in formatted
    
    def test_sparse_data_prompt_has_no_empty_categories(self):
        """Regression test: with only Age/Gender/Diagnosis, the prompt should
        not mention Symptoms/Medications/Vitals/Lab_Results/etc. at all, and
        should instruct the model to keep the summary short rather than pad it."""
        patient_dict = {
            "Age": "45 years",
            "Gender": "Male",
            "Diagnosis": "Type 2 Diabetes",
            "Symptoms": [],
            "Medications": [],
            "Surgeries": [],
            "Allergies": [],
            "Medical_Warnings": [],
            "Problems": [],
            "Vitals": {},
            "Lab_Results": {},
        }
        formatted = format_patient_data(patient_dict)
        prompt = get_user_prompt(patient_dict)

        # None of the empty categories should leak into the formatted data
        for label in ["Symptoms:", "Medications:", "Vital signs:", "Lab results:",
                      "Allergies:", "Medical warnings:", "Comorbidities:", "Surgeries:"]:
            assert label not in formatted

        # The prompt should explicitly tell the model not to invent extra detail
        assert "do not invent" in prompt.lower() or "brief 1-2 sentence" in prompt.lower()

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



class TestHallucinationGuard:
    """Test the post-generation fabrication check in summarization_service."""

    def test_flags_numbers_not_in_source(self):
        from app.services.summarization_service import find_hallucinated_numbers

        patient_data = {"Age": "45 years", "Gender": "Male", "Diagnosis": "Type 2 Diabetes"}
        fabricated_summary = (
            "A 45-year-old male with type 2 diabetes, HbA1c of 8.2%, "
            "BP 135/82, on metformin 500 mg."
        )
        suspects = find_hallucinated_numbers(patient_data, fabricated_summary)
        # 8.2, 135/82, 500 were never in the source data
        assert "8.2%" in suspects or "8.2" in suspects
        assert "500" in suspects

    def test_no_false_positive_when_values_match_source(self):
        from app.services.summarization_service import find_hallucinated_numbers

        patient_data = {
            "Age": "45 years",
            "Gender": "Male",
            "Diagnosis": "Type 2 Diabetes",
            "Vitals": {"BP": "120/80", "HR": "72"},
        }
        summary = "A 45-year-old male with type 2 diabetes, BP 120/80, HR 72."
        suspects = find_hallucinated_numbers(patient_data, summary)
        assert suspects == set()


class TestSparseInputBypass:
    """Regression tests for skipping the LLM entirely on demographics-only input."""

    SPARSE_PATIENT = {
        "Age": "45 years", "Gender": "Male", "Diagnosis": "Type 2 Diabetes",
        "Symptoms": [], "Medications": [], "Surgeries": [], "Allergies": [],
        "Medical_Warnings": [], "Problems": [], "Vitals": {}, "Lab_Results": {},
    }

    def test_detects_sparse_input(self):
        from app.services.summarization_service import is_sparse_input
        assert is_sparse_input(self.SPARSE_PATIENT) is True

    def test_not_sparse_when_any_field_populated(self):
        from app.services.summarization_service import is_sparse_input
        patient = dict(self.SPARSE_PATIENT, Symptoms=["fatigue"])
        assert is_sparse_input(patient) is False

    def test_template_summary_has_no_fabricated_content(self):
        from app.services.summarization_service import build_sparse_summary, find_hallucinated_categories
        summary = build_sparse_summary(self.SPARSE_PATIENT)
        assert "45 years" in summary
        assert "Type 2 Diabetes" in summary
        # The template itself must never trip its own fabrication guard
        assert find_hallucinated_categories(self.SPARSE_PATIENT, summary) == set()

    def test_category_guard_catches_reported_hallucination(self):
        """The exact fabricated output seen in production for the sparse case."""
        from app.services.summarization_service import find_hallucinated_categories
        bad_summary = (
            "A 45-year-old male with Type 2 Diabetes presents with a history of "
            "hyperglycemia and a family history of cardiovascular disease. "
            "No additional clinical details are provided."
        )
        flagged = find_hallucinated_categories(self.SPARSE_PATIENT, bad_summary)
        assert "Problems" in flagged  # "family history of...", "history of..."
        assert "Symptoms" in flagged  # "presents with"

    def test_category_guard_no_false_positive_on_legit_data(self):
        from app.services.summarization_service import find_hallucinated_categories
        patient = dict(self.SPARSE_PATIENT, Symptoms=["fatigue", "polyuria"])
        summary = "A 45-year-old male with Type 2 Diabetes presents with fatigue and polyuria."
        assert find_hallucinated_categories(patient, summary) == set()
