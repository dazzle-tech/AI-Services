"""Tests for analysis output normalization."""
from app.services.output_normalizer import normalize_analysis_result

PATIENT_DATA = {
    "patient_info": {
        "name": "Jane Doe",
        "age": 58,
        "gender": "Female",
        "weight_kg": 65,
        "admission_reason": "Suspected UTI",
        "comorbidities": ["Diabetes"],
    },
    "hourly_data": [],
}


def test_flat_llm_output_is_normalized_to_schema():
    """Flat demographics and aliases should map to the canonical structure."""
    raw = {
        "assessment_timestamp": "2026-03-15T12:00:00Z",
        "patient_id": "JD001",
        "patient_name": "Jane Doe",
        "age": 58,
        "gender": "Female",
        "weight": 65,
        "admission_reason": "Suspected UTI",
        "comorbidities": ["Diabetes"],
        "status_summary": "Stable patient with suspected UTI",
        "sirs_criteria_met": True,
        "qsofa_score": 0,
        "patient_vitals": {
            "temp": {"value": 36.5, "unit": "°C", "status": "normal", "trend": "stable"}
        },
        "current_labs": {
            "lactate": {"value": 2.5, "unit": "mmol/L", "status": "normal", "trend": "stable"}
        },
        "timeline_analysis": [],
        "organ_dysfunction": {},
        "watchlist": [],
        "risk_factors": {},
        "forecast_24h": {},
        "sepsis_probability_24h": {},
        "recommended_actions": [],
        "flags": {},
    }

    result = normalize_analysis_result(raw, PATIENT_DATA)

    assert "patient_snapshot" in result
    assert result["patient_snapshot"]["name"] == "Jane Doe"
    assert result["patient_snapshot"]["age"] == 58
    assert result["patient_snapshot"]["weight_kg"] == 65
    assert "name" not in result
    assert "patient_name" not in result
    assert "age" not in result
    assert isinstance(result["status_summary"], dict)
    assert result["status_summary"]["one_line"] == "Stable patient with suspected UTI"
    assert result["status_summary"]["sirs_criteria_met"] is True
    assert "Temp" in result["current_vitals"]
    assert "Lactate" in result["current_labs"]
    assert "patient_vitals" not in result


def test_input_patient_info_populates_snapshot_when_llm_omits_it():
    """Demographics from request input should always appear in patient_snapshot."""
    raw = {
        "status_summary": {"overall_condition": "stable", "one_line": "OK"},
        "current_vitals": {},
        "current_labs": {},
    }

    result = normalize_analysis_result(raw, PATIENT_DATA)

    snapshot = result["patient_snapshot"]
    assert snapshot["name"] == "Jane Doe"
    assert snapshot["gender"] == "Female"
    assert snapshot["comorbidities"] == ["Diabetes"]


def test_output_always_has_all_top_level_keys():
    """Every analysis response should expose the same top-level keys."""
    raw = {"patient_snapshot": {"name": "Test"}}

    result = normalize_analysis_result(raw, PATIENT_DATA)

    expected_keys = {
        "patient_snapshot",
        "status_summary",
        "current_vitals",
        "current_labs",
        "timeline_analysis",
        "organ_dysfunction",
        "watchlist",
        "risk_factors",
        "forecast_24h",
        "sepsis_probability_24h",
        "recommended_actions",
        "flags",
    }
    assert set(result.keys()) == expected_keys
