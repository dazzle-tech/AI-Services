"""Tests for normalization"""
import pytest
from app.domain.normalization import ConceptNormalizer


def test_normalizer_basic():
    """Test basic normalization"""
    mappings = {
        "heart_rate": {
            "item_names": ["heart rate", "hr", "pulse"],
            "item_codes": ["HR", "PULSE"]
        }
    }
    normalizer = ConceptNormalizer(mappings)
    
    assert normalizer.normalize("heart rate") == "heart_rate"
    assert normalizer.normalize("HR") == "heart_rate"
    assert normalizer.normalize("pulse") == "heart_rate"
    assert normalizer.normalize("Heart Rate") == "heart_rate"  # Case insensitive
    assert normalizer.normalize("unknown") is None


def test_normalizer_partial_match():
    """Test partial matching"""
    mappings = {
        "heart_rate": {
            "item_names": ["heart rate"],
            "item_codes": []
        }
    }
    normalizer = ConceptNormalizer(mappings)
    
    # Should match partial
    assert normalizer.normalize("heart rate measurement") == "heart_rate"


def test_normalizer_code_priority():
    """Test that codes take priority over names"""
    mappings = {
        "heart_rate": {
            "item_names": ["heart rate"],
            "item_codes": ["HR"]
        },
        "respiratory_rate": {
            "item_names": ["hr"],  # Ambiguous name
            "item_codes": []
        }
    }
    normalizer = ConceptNormalizer(mappings)
    
    # Code should match heart_rate, not respiratory_rate
    assert normalizer.normalize("hr", item_code="HR") == "heart_rate"
