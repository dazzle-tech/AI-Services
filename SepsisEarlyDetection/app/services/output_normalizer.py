"""Normalize LLM analysis output to a consistent schema structure."""
from copy import deepcopy
from typing import Any, Dict, List, Optional

TOP_LEVEL_KEYS = [
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
]

PATIENT_SNAPSHOT_KEYS = [
    "patient_id",
    "name",
    "age",
    "gender",
    "weight_kg",
    "admission_reason",
    "comorbidities",
    "current_hour",
    "assessment_timestamp",
]

FLAT_TO_SNAPSHOT = {
    "patient_id": "patient_id",
    "patient_name": "name",
    "name": "name",
    "age": "age",
    "gender": "gender",
    "weight": "weight_kg",
    "weight_kg": "weight_kg",
    "admission_reason": "admission_reason",
    "comorbidities": "comorbidities",
    "current_hour": "current_hour",
    "assessment_timestamp": "assessment_timestamp",
}

FLAT_TO_STATUS = {
    "sirs_criteria_met": "sirs_criteria_met",
    "qsofa_score": "qsofa_score",
    "sofa_score": "sofa_score",
    "sepsis_3_criteria_met": "sepsis_3_criteria_met",
}

VITAL_ALIASES = {
    "hr": "HR",
    "heart_rate": "HR",
    "resp": "Resp",
    "respiratory_rate": "Resp",
    "sbp": "SBP",
    "dbp": "DBP",
    "map": "MAP",
    "o2sat": "O2Sat",
    "spo2": "O2Sat",
    "temp": "Temp",
    "temperature": "Temp",
    "etco2": "EtCO2",
    "bp": "SBP",
}

LAB_ALIASES = {
    "lactate": "Lactate",
    "wbc": "WBC",
    "platelets": "Platelets",
    "creatinine": "Creatinine",
    "bilirubin_total": "Bilirubin_total",
    "hco3": "HCO3",
    "bun": "BUN",
    "hct": "Hct",
}

VITALS_SOURCE_KEYS = ("current_vitals", "patient_vitals")

STATUS_SUMMARY_DEFAULTS = {
    "overall_condition": "guarded",
    "one_line": "",
    "narrative": "",
    "sirs_criteria_met": 0,
    "qsofa_score": 0,
    "sofa_score": 0,
    "sepsis_3_criteria_met": False,
}

ORGAN_SYSTEMS = [
    "cardiovascular",
    "respiratory",
    "renal",
    "hepatic",
    "hematologic",
    "metabolic",
]


def _coalesce(*values: Any) -> Any:
    """Return the first non-None value, or the last value if all are None."""
    for value in values:
        if value is not None:
            return value
    return values[-1] if values else None


def _normalize_key(key: str, aliases: Dict[str, str]) -> str:
    """Map a parameter key to its canonical schema name."""
    if key in aliases.values():
        return key
    return aliases.get(key.lower(), key)


def _normalize_parameter_dict(
    data: Any, aliases: Dict[str, str]
) -> Dict[str, Any]:
    """Normalize vital/lab dict keys to schema casing."""
    if not isinstance(data, dict):
        return {}
    normalized: Dict[str, Any] = {}
    for key, value in data.items():
        canonical = _normalize_key(key, aliases)
        if canonical not in normalized:
            normalized[canonical] = value
    return normalized


def _extract_flat_snapshot_fields(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Pull patient demographics from flat top-level LLM fields."""
    extracted: Dict[str, Any] = {}
    for flat_key, snap_key in FLAT_TO_SNAPSHOT.items():
        if flat_key in raw and snap_key not in extracted:
            extracted[snap_key] = raw[flat_key]
    return extracted


def _build_patient_snapshot(
    patient_data: Dict[str, Any], raw: Dict[str, Any]
) -> Dict[str, Any]:
    """Build patient_snapshot from input data and LLM output."""
    info = patient_data.get("patient_info", {})
    hourly = patient_data.get("hourly_data", [])
    last_hour = hourly[-1] if hourly else {}

    llm_snapshot = raw.get("patient_snapshot")
    llm_snapshot = llm_snapshot if isinstance(llm_snapshot, dict) else {}
    flat_fields = _extract_flat_snapshot_fields(raw)

    patient_id = _coalesce(
        info.get("patient_id"),
        llm_snapshot.get("patient_id"),
        flat_fields.get("patient_id"),
        "",
    )
    if patient_id is not None:
        patient_id = str(patient_id)

    return {
        "patient_id": patient_id or "",
        "name": _coalesce(info.get("name"), llm_snapshot.get("name"), flat_fields.get("name"), ""),
        "age": _coalesce(info.get("age"), llm_snapshot.get("age"), flat_fields.get("age"), 0),
        "gender": _coalesce(info.get("gender"), llm_snapshot.get("gender"), flat_fields.get("gender"), ""),
        "weight_kg": _coalesce(
            info.get("weight_kg"), llm_snapshot.get("weight_kg"), flat_fields.get("weight_kg"), 0
        ),
        "admission_reason": _coalesce(
            info.get("admission_reason"),
            llm_snapshot.get("admission_reason"),
            flat_fields.get("admission_reason"),
            "",
        ),
        "comorbidities": _coalesce(
            info.get("comorbidities"),
            llm_snapshot.get("comorbidities"),
            flat_fields.get("comorbidities"),
            [],
        )
        or [],
        "current_hour": _coalesce(
            last_hour.get("hour"),
            llm_snapshot.get("current_hour"),
            flat_fields.get("current_hour"),
            0,
        ),
        "assessment_timestamp": _coalesce(
            last_hour.get("timestamp"),
            llm_snapshot.get("assessment_timestamp"),
            flat_fields.get("assessment_timestamp"),
            "",
        )
        or "",
    }


def _normalize_status_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure status_summary is always an object with expected fields."""
    summary = raw.get("status_summary")
    if isinstance(summary, str):
        summary = {
            "one_line": summary,
            "narrative": summary,
            "overall_condition": "guarded",
        }
    elif not isinstance(summary, dict):
        summary = {}

    for flat_key, summary_key in FLAT_TO_STATUS.items():
        if flat_key in raw and summary_key not in summary:
            summary[summary_key] = raw[flat_key]

    return {**STATUS_SUMMARY_DEFAULTS, **summary}


def _get_vitals(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract vitals from whichever key the LLM used."""
    for key in VITALS_SOURCE_KEYS:
        if key in raw and isinstance(raw[key], dict):
            return _normalize_parameter_dict(raw[key], VITAL_ALIASES)
    return {}


def _get_labs(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract labs and normalize key casing."""
    labs = raw.get("current_labs")
    if isinstance(labs, dict):
        return _normalize_parameter_dict(labs, LAB_ALIASES)
    return {}


def _default_organ_dysfunction() -> Dict[str, Dict[str, str]]:
    return {system: {"status": "normal", "notes": ""} for system in ORGAN_SYSTEMS}


def _merge_section(
    raw: Dict[str, Any], key: str, default: Any
) -> Any:
    """Return a section from raw output or a deep-copied default."""
    value = raw.get(key)
    if value is None:
        return deepcopy(default)
    if isinstance(default, dict) and isinstance(value, dict):
        return {**deepcopy(default), **value}
    return value


def normalize_analysis_result(
    raw: Dict[str, Any],
    patient_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalize LLM output to a consistent analysis structure.

    Ensures patient demographics always appear under patient_snapshot,
    status_summary is always an object, and top-level keys match the schema.
    """
    normalized: Dict[str, Any] = {
        "patient_snapshot": _build_patient_snapshot(patient_data, raw),
        "status_summary": _normalize_status_summary(raw),
        "current_vitals": _get_vitals(raw),
        "current_labs": _get_labs(raw),
        "timeline_analysis": raw.get("timeline_analysis")
        if isinstance(raw.get("timeline_analysis"), list)
        else [],
        "organ_dysfunction": _merge_section(
            raw, "organ_dysfunction", _default_organ_dysfunction()
        ),
        "watchlist": raw.get("watchlist")
        if isinstance(raw.get("watchlist"), list)
        else [],
        "risk_factors": _merge_section(
            raw,
            "risk_factors",
            {
                "infection_source_suspected": "",
                "immunocompromised": False,
                "age_risk": False,
                "comorbidity_burden": "low",
                "contributing_factors": [],
            },
        ),
        "forecast_24h": _merge_section(
            raw,
            "forecast_24h",
            {
                "expected_trajectory": "stable",
                "narrative": "",
                "key_decision_points": [],
                "intervention_urgency": "routine",
            },
        ),
        "sepsis_probability_24h": _merge_section(
            raw,
            "sepsis_probability_24h",
            {
                "probability": 0,
                "risk_level": "low",
                "confidence": "low",
                "primary_drivers": [],
                "mitigating_factors": [],
            },
        ),
        "recommended_actions": raw.get("recommended_actions")
        if isinstance(raw.get("recommended_actions"), list)
        else [],
        "flags": _merge_section(
            raw,
            "flags",
            {
                "escalate_care": False,
                "repeat_labs_needed": False,
                "imaging_recommended": False,
                "culture_recommended": False,
                "antibiotic_consideration": False,
                "fluid_resuscitation_needed": False,
                "vasopressor_consideration": False,
                "icu_transfer_recommended": False,
            },
        ),
    }

    return {key: normalized[key] for key in TOP_LEVEL_KEYS}
