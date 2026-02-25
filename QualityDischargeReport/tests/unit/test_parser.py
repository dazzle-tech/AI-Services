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

