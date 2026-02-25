"""Tests for trend computation"""
import pytest
from datetime import datetime, timedelta
from app.domain.input_models import (
    ICURequestPayload, PatientInfo, EncounterInfo, TimeWindow, FlowsheetEntry
)
from app.domain.normalization import ConceptNormalizer
from app.domain.trends import build_clinical_summary


def test_basic_trend_computation():
    """Test basic trend computation"""
    # Setup
    now = datetime.now()
    time_start = now - timedelta(hours=24)
    time_end = now
    
    mappings = {
        "heart_rate": {
            "item_names": ["heart rate", "hr"],
            "item_codes": ["HR"]
        }
    }
    normalizer = ConceptNormalizer(mappings)
    
    # Create payload
    payload = ICURequestPayload(
        patient=PatientInfo(id="P1"),
        encounter=EncounterInfo(id="E1"),
        time_window=TimeWindow(start=time_start, end=time_end),
        flowsheet=[
            FlowsheetEntry(
                timestamp=time_start + timedelta(hours=1),
                item_name="heart rate",
                value="80",
                unit="bpm"
            ),
            FlowsheetEntry(
                timestamp=time_start + timedelta(hours=12),
                item_name="heart rate",
                value="90",
                unit="bpm"
            ),
            FlowsheetEntry(
                timestamp=time_start + timedelta(hours=23),
                item_name="heart rate",
                value="85",
                unit="bpm"
            )
        ]
    )
    
    # Build summary
    summary = build_clinical_summary(payload, normalizer)
    
    # Assertions
    assert summary.heart_rate is not None
    assert summary.heart_rate.last == 85.0
    assert summary.heart_rate.min == 80.0
    assert summary.heart_rate.max == 90.0
    assert summary.heart_rate.unit == "bpm"


def test_trend_with_out_of_window_data():
    """Test that out-of-window data is excluded"""
    now = datetime.now()
    time_start = now - timedelta(hours=24)
    time_end = now
    
    mappings = {
        "heart_rate": {
            "item_names": ["heart rate"],
            "item_codes": []
        }
    }
    normalizer = ConceptNormalizer(mappings)
    
    payload = ICURequestPayload(
        patient=PatientInfo(id="P1"),
        encounter=EncounterInfo(id="E1"),
        time_window=TimeWindow(start=time_start, end=time_end),
        flowsheet=[
            FlowsheetEntry(
                timestamp=time_start - timedelta(hours=1),  # Before window
                item_name="heart rate",
                value="70",
                unit="bpm"
            ),
            FlowsheetEntry(
                timestamp=time_start + timedelta(hours=12),  # In window
                item_name="heart rate",
                value="85",
                unit="bpm"
            ),
            FlowsheetEntry(
                timestamp=time_end + timedelta(hours=1),  # After window
                item_name="heart rate",
                value="90",
                unit="bpm"
            )
        ]
    )
    
    summary = build_clinical_summary(payload, normalizer)
    
    # Should only include the in-window value
    assert summary.heart_rate is not None
    assert summary.heart_rate.last == 85.0
    assert summary.heart_rate.min == 85.0
    assert summary.heart_rate.max == 85.0
