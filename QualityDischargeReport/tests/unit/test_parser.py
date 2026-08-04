"""Unit tests for parser."""

import pytest
from src.services.discharge_qa.parser import DischargeReportParser


def test_parse_text_report():
    """Test parsing text discharge report."""
    parser = DischargeReportParser()
    
    text = """
    DISCHARGE SUMMARY
    Age: 65
    Sex: Male
    Diagnosis: MI
    Medications: Aspirin 81mg daily
    """
    
    result = parser.parse(text)
    
    assert result["format"] == "text"
    assert "content" in result
    assert "patient_info" in result["content"] or "diagnoses" in result["content"]


def test_parse_patient_info_from_document_header():
    """Age and gender should be parsed even without a Patient Information section."""
    parser = DischargeReportParser()
    text = (
        "DISCHARGE SUMMARY\n\n"
        "Patient ID: 1000\n"
        "Age: 55 years\n"
        "Gender: MALE\n"
        "Admission Date: 2026-05-31\n\n"
        "CHIEF COMPLAINT\n"
        "Chest pain\n"
    )

    result = parser.parse(text)

    patient_info = result["content"]["patient_info"]
    assert patient_info["age"] == 55
    assert patient_info["sex"].upper() == "MALE"


def test_parse_allergies_from_narrative_sentence():
    """Narrative allergy sentences should normalize to individual allergy terms."""
    parser = DischargeReportParser()

    allergies = parser._extract_allergies("The patient is allergic to Med22 and test.")

    assert allergies == ["Med22", "test"]


def test_parse_json_report():
    """Test parsing JSON discharge report."""
    parser = DischargeReportParser()
    
    json_data = {
        "patient_info": {"age": 65},
        "diagnoses": {"primary_diagnosis": "MI"}
    }
    
    result = parser.parse(json_data)
    
    assert result["format"] == "json"
    assert "content" in result


def test_normalize_section_names():
    """Test section name normalization."""
    parser = DischargeReportParser()
    
    content = {
        "Patient Demographics": {"age": 65},
        "Diagnosis": {"primary": "MI"}
    }
    
    normalized = parser._normalize_structure(content)
    
    assert "patient_info" in normalized or "diagnoses" in normalized

