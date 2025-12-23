"""Unit tests for normalizer."""

import pytest
from src.services.discharge_qa.normalizer import DischargeReportNormalizer


def test_normalize_medications():
    """Test medication normalization."""
    normalizer = DischargeReportNormalizer()
    
    meds = ["Aspirin 81mg PO daily", "Clopidogrel 75mg PO BID"]
    
    normalized = normalizer.normalize_medications(meds)
    
    assert len(normalized) == 2
    assert normalized[0]["name"] is not None
    assert "dose" in normalized[0] or normalized[0].get("dose") is not None


def test_normalize_vitals():
    """Test vitals normalization."""
    normalizer = DischargeReportNormalizer()
    
    vitals_str = "BP: 120/80, HR: 72, RR: 16, Temp: 98.6, O2 Sat: 98%"
    
    normalized = normalizer.normalize_vitals(vitals_str)
    
    assert normalized["bp"] is not None
    assert normalized["hr"] is not None


def test_normalize_vitals_dict():
    """Test vitals dictionary normalization."""
    normalizer = DischargeReportNormalizer()
    
    vitals = {
        "blood_pressure": "120/80",
        "heart_rate": "72"
    }
    
    normalized = normalizer.normalize_vitals(vitals)
    
    assert normalized["bp"] == "120/80"
    assert normalized["hr"] == "72"

