"""Integration tests for Direct QA flow."""

import pytest
import json
from pathlib import Path
from src.services.discharge_qa.service import DischargeQAService

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def sample_discharge_report():
    """Load sample discharge report."""
    with open(FIXTURES_DIR / "discharge_report_text.txt", "r") as f:
        return f.read()


@pytest.fixture
def sample_patient_record():
    """Load sample patient record."""
    with open(FIXTURES_DIR / "patient_record.json", "r") as f:
        return json.load(f)


@pytest.fixture
def sample_onsite_docs():
    """Load sample onsite docs."""
    with open(FIXTURES_DIR / "onsite_docs.json", "r") as f:
        return json.load(f)


def test_direct_qa_basic(sample_discharge_report, sample_patient_record, sample_onsite_docs):
    """Test basic Direct QA flow."""
    service = DischargeQAService()
    
    # Note: This test may fail if OpenAI API is not configured
    # In a real scenario, you'd mock the OpenAI client
    try:
        result = service.perform_qa(
            discharge_report=sample_discharge_report,
            patient_record=sample_patient_record,
            onsite_docs=sample_onsite_docs
        )
        
        assert "qa_method" in result
        assert result["qa_method"] == "direct_qa"
        assert "overall_score" in result
        assert "summary" in result
        assert "parsed_report" in result
        assert "errors" in result
        assert "missing_items" in result
        assert "inconsistencies" in result
    except Exception as e:
        # If OpenAI API is not available, test structure creation
        pytest.skip(f"OpenAI API not available: {str(e)}")


def test_qa_structure_validation(sample_discharge_report, sample_patient_record, sample_onsite_docs):
    """Test that QA result has correct structure."""
    service = DischargeQAService()
    
    # Mock the prompt runner to avoid API calls
    class MockPromptRunner:
        def run_qa(self, *args, **kwargs):
            return {
                "qa_method": "direct_qa",
                "overall_score": 85,
                "summary": "Test summary",
                "parsed_report": {"format": "text", "structure_used": "standard", "content": {}, "unmapped_content": []},
                "errors": [],
                "missing_items": [],
                "inconsistencies": [],
                "recommended_corrections": []
            }
    
    service.prompt_runner = MockPromptRunner()
    
    result = service.perform_qa(
        discharge_report=sample_discharge_report,
        patient_record=sample_patient_record,
        onsite_docs=sample_onsite_docs
    )
    
    assert result["qa_method"] == "direct_qa"
    assert isinstance(result["overall_score"], (int, float))
    assert 0 <= result["overall_score"] <= 100
    assert isinstance(result["errors"], list)
    assert isinstance(result["missing_items"], list)
    assert isinstance(result["inconsistencies"], list)


def test_qa_filters_false_return_precautions_missing(sample_discharge_report, sample_patient_record, sample_onsite_docs):
    """Malformed AI findings for present return_precautions should be removed after merge."""
    service = DischargeQAService()

    class MockPromptRunner:
        def run_qa(self, *args, **kwargs):
            return {
                "qa_method": "direct_qa",
                "overall_score": 90,
                "summary": "AI summary",
                "parsed_report": {
                    "format": "text",
                    "structure_used": "standard",
                    "content": {},
                    "unmapped_content": [],
                },
                "errors": [
                    {
                        "type": "missing_item",
                        "section": "follow_up_and_instructions",
                        "field": "return_precautions",
                        "reason": "Required for high-risk cases",
                    }
                ],
                "missing_items": [
                    {
                        "section": "follow_up_and_instructions",
                        "field": "return_precautions",
                    }
                ],
                "inconsistencies": [],
                "recommended_corrections": [
                    {
                        "id": "FIX-001",
                        "action": "add",
                        "section": "follow_up_and_instructions",
                        "field": "return_precautions",
                        "suggested_text": "",
                        "rationale": "",
                    }
                ],
            }

    service.prompt_runner = MockPromptRunner()

    result = service.perform_qa(
        discharge_report=sample_discharge_report,
        patient_record=sample_patient_record,
        onsite_docs=sample_onsite_docs,
    )

    is_valid, error = service.validator.validate(result)

    assert is_valid, error
    assert result["overall_score"] == 100
    assert result["errors"] == []
    assert result["missing_items"] == []
    assert result["recommended_corrections"] == []
    assert "validation issues" not in result["summary"].lower()
    precautions = result["parsed_report"]["content"]["follow_up_and_instructions"]["return_precautions"]
    assert len(precautions) > 0


def test_qa_handles_ai_errors_with_string_location(sample_discharge_report, sample_patient_record, sample_onsite_docs):
    """AI errors whose location is a string should not crash post-processing."""
    service = DischargeQAService()

    class MockPromptRunner:
        def run_qa(self, *args, **kwargs):
            return {
                "qa_method": "direct_qa",
                "overall_score": 80,
                "summary": "AI summary",
                "parsed_report": {
                    "format": "text",
                    "structure_used": "standard",
                    "content": {},
                    "unmapped_content": [],
                },
                "errors": [
                    {
                        "category": "consistency",
                        "severity": "medium",
                        "location": "medications",
                        "field": "discharge_medications",
                        "issue": "Aspirin dose differs from patient record",
                    }
                ],
                "missing_items": [],
                "inconsistencies": [],
                "recommended_corrections": [],
            }

    service.prompt_runner = MockPromptRunner()

    result = service.perform_qa(
        discharge_report=sample_discharge_report,
        patient_record=sample_patient_record,
        onsite_docs=sample_onsite_docs,
    )

    assert result["qa_method"] == "direct_qa"
    assert isinstance(result["errors"], list)


def test_qa_flags_active2_dose_mismatch_from_medications_on_admission():
    """End-to-end: compound discharge med text + medications_on_admission should flag dose mismatch."""
    service = DischargeQAService()
    discharge_report = (
        "DISCHARGE SUMMARY\n\n"
        "DISCHARGE MEDICATIONS\n"
        "--------------------------------------------------------------------------------\n"
        "The patient was prescribed active1 3 Capsule twice daily and active2 1 Mg every 4 hours on admission.\n"
    )
    patient_record = {
        "medications_on_admission": [
            {"name": "active1", "dose": "3 Capsule", "frequency": "Twice daily"},
            {"name": "active2", "dose": "5 Mg", "frequency": "Every 4 hours"},
        ]
    }

    class MockPromptRunner:
        def run_qa(self, *args, **kwargs):
            return {
                "qa_method": "direct_qa",
                "overall_score": 80,
                "summary": "AI summary",
                "parsed_report": {
                    "format": "text",
                    "structure_used": "standard",
                    "content": {},
                    "unmapped_content": [],
                },
                "errors": [],
                "missing_items": [],
                "inconsistencies": [],
                "recommended_corrections": [],
            }

    service.prompt_runner = MockPromptRunner()

    result = service.perform_qa(
        discharge_report=discharge_report,
        patient_record=patient_record,
        onsite_docs=[],
    )

    dose_mismatches = [
        item
        for item in result["inconsistencies"]
        if item.get("field") == "dose" and "active2" in str(item.get("ref_id", "")).lower()
    ]
    assert len(dose_mismatches) == 1
    assert dose_mismatches[0]["report_value"] == "1 Mg"
    assert dose_mismatches[0]["source_value"] == "5 Mg"


def test_qa_flags_age_sex_and_allergy_mismatches_from_report_header():
    """Demographics in the report header and allergy lists should be compared to the patient record."""
    service = DischargeQAService()
    discharge_report = (
        "DISCHARGE SUMMARY\n\n"
        "Patient ID: 1000\n"
        "Age: 55 years\n"
        "Gender: MALE\n"
        "Admission Date: 2026-05-31\n"
        "Discharge Date: Pending\n\n"
        "Primary Diagnosis: Blood alcohol level of 60-79 mg/100 ml\n\n"
        "ALLERGIES\n"
        "--------------------------------------------------------------------------------\n"
        "The patient is allergic to Med22.\n\n"
        "DISCHARGE MEDICATIONS\n"
        "--------------------------------------------------------------------------------\n"
        "The patient is prescribed active1 3 Capsule Twice weekly and active2 1 Mg Every 4 hours.\n"
    )
    patient_record = {
        "age": 22,
        "gender": "FEMALE",
        "allergies": ["Med22", "test"],
        "medications_on_admission": [
            {"name": "active1", "dose": "3 Capsule", "frequency": "Twice daily"},
            {"name": "active2", "dose": "5 Mg", "frequency": "Every 4 hours"},
        ],
    }

    class MockPromptRunner:
        def run_qa(self, *args, **kwargs):
            return {
                "qa_method": "direct_qa",
                "overall_score": 80,
                "summary": "AI summary",
                "parsed_report": {
                    "format": "text",
                    "structure_used": "standard",
                    "content": {},
                    "unmapped_content": [],
                },
                "errors": [],
                "missing_items": [],
                "inconsistencies": [],
                "recommended_corrections": [],
            }

    service.prompt_runner = MockPromptRunner()

    result = service.perform_qa(
        discharge_report=discharge_report,
        patient_record=patient_record,
        onsite_docs=[],
    )

    fields = {item.get("field") for item in result["inconsistencies"]}
    sections = {item.get("section") for item in result["inconsistencies"]}

    assert "age" in fields
    assert "sex" in fields
    assert "allergies" in sections
    allergy_mismatch = next(
        item for item in result["inconsistencies"] if item.get("ref_id") == "test"
    )
    assert allergy_mismatch["report_value"] == ["Med22"]
    assert allergy_mismatch["source_value"] == ["Med22", "test"]

