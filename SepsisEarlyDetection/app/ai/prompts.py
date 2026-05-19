"""Prompt templates for SepsisSentinel sepsis risk assessment."""
import json
from typing import Any, Dict, List


def _format_list(value: Any) -> str:
    """Convert list-like patient metadata into a display string."""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "None reported"
    if value in (None, ""):
        return "None reported"
    return str(value)


def build_system_prompt(context: str, schema: str) -> str:
    """Construct the system prompt for the GPT-4o API call.

    Args:
        context: Clinical research context text.
        schema: JSON output schema text.

    Returns:
        Complete system prompt string.
    """
    return (
        "You are SepsisSentinel, a clinical AI sepsis early detection "
        "system. You will receive a patient's complete 24-hour hourly "
        "time-series data including vitals and laboratory values, along "
        "with clinical research context on sepsis detection.\n\n"
        "YOUR TASK:\n"
        "Analyse the provided patient data and return a comprehensive "
        "sepsis risk assessment. Follow these instructions precisely:\n\n"
        "TREND ANALYSIS:\n"
        "- Analyse the full hourly time-series as a trend analysis, not "
        "just the latest values.\n"
        "- Identify the direction and rate of change for every vital sign "
        "and lab value across all 24 hours.\n\n"
        "SCORING:\n"
        "- Compute the qSOFA score: respiratory rate >=22 (1 point), "
        "altered mentation (1 point), systolic blood pressure <=100 "
        "(1 point). Report the total (0-3).\n"
        "- Count SIRS criteria met: temperature <36 or >38 degrees C, "
        "heart rate >90 bpm, respiratory rate >20 breaths/min, WBC <4 or "
        ">12 (x10^3/uL). Report the count (0-4).\n"
        "- Estimate the SOFA score from available labs and vitals across "
        "all six organ systems.\n\n"
        "THRESHOLD CROSSING:\n"
        "- Identify the exact hour each of these clinical thresholds was "
        "FIRST crossed:\n"
        "  lactate >=2 mmol/L, HR >100 bpm, MAP <70 mmHg, "
        "Temp >38.3 degrees C, RR >22 breaths/min, SBP <100 mmHg.\n"
        "- If a threshold was never crossed, do not include it.\n\n"
        "ORGAN DYSFUNCTION:\n"
        "- Assess organ dysfunction across six systems: cardiovascular, "
        "respiratory, renal, hepatic, hematologic, metabolic.\n"
        "- For each system report status (normal, impaired, or failing) "
        "and clinical notes explaining your assessment.\n\n"
        "WATCHLIST:\n"
        "- Populate the watchlist ONLY with parameters that are abnormal, "
        "borderline, or showing a concerning rate of change.\n"
        "- Do NOT include parameters that are normal and stable.\n\n"
        "FORECAST:\n"
        "- Generate a 24-hour probabilistic forecast with hour-specific "
        "decision triggers.\n"
        "- Assign an expected trajectory (improving, stable, "
        "deteriorating, or critical).\n"
        "- Set the intervention urgency (routine, urgent, or emergent).\n\n"
        "RECOMMENDED ACTIONS:\n"
        "- Assign prioritised clinical actions with priorities: immediate, "
        "within_1h, within_4h, or routine.\n"
        "- Each action must have a rationale.\n\n"
        "FLAGS:\n"
        "- Set all boolean flags for clinical decision support: "
        "escalate_care, repeat_labs_needed, imaging_recommended, "
        "culture_recommended, antibiotic_consideration, "
        "fluid_resuscitation_needed, vasopressor_consideration, "
        "icu_transfer_recommended.\n\n"
        "OUTPUT SCHEMA BREAKDOWN:\n"
        "Your response must be a single JSON object with these top-level "
        "keys. Here is what each section requires:\n\n"
        '1. "patient_snapshot": Echo back the patient demographics. '
        "Fields: patient_id, name, age, gender, weight_kg, "
        "admission_reason, comorbidities (array), current_hour (the last "
        "hour number in the data), assessment_timestamp (timestamp of the "
        "last data point).\n\n"
        '2. "status_summary": Overall clinical picture. Fields:\n'
        '   - overall_condition: one of "stable", "guarded", or '
        '"critical"\n'
        "   - one_line: a single-sentence clinical summary\n"
        "   - narrative: a detailed 3-5 sentence clinical narrative\n"
        "   - sirs_criteria_met: integer 0-4, count of SIRS criteria met "
        "at the latest hour\n"
        "   - qsofa_score: integer 0-3\n"
        "   - sofa_score: integer 0-24, estimated from available data\n"
        "   - sepsis_3_criteria_met: boolean, true if suspected infection "
        "+ SOFA increase >=2\n\n"
        '3. "current_vitals": Latest-hour vital signs. Keys: HR, Resp, '
        "SBP, DBP, MAP, O2Sat, Temp, EtCO2. Each is an object with: "
        'value (number), unit (string), status (one of "normal"/"warning"'
        '/"critical"), trend (one of "improving"/"stable"/"worsening" '
        "based on the full 24h trajectory).\n\n"
        '4. "current_labs": Latest-hour laboratory values. Keys: Lactate, '
        "WBC, Platelets, Creatinine, Bilirubin_total, HCO3, BUN, Hct. "
        "Same sub-fields as current_vitals: value, unit, status, trend.\n\n"
        '5. "timeline_analysis": Array of significant clinical events '
        "across the 24 hours. Each entry: time (\"Hour N\"), event "
        "(description), affected_parameters (array of parameter names), "
        'severity ("normal"/"warning"/"critical"), clinical_significance '
        "(explanation). Include only hours where something clinically "
        "notable occurred.\n\n"
        '6. "organ_dysfunction": Object with keys: cardiovascular, '
        "respiratory, renal, hepatic, hematologic, metabolic. Each has: "
        'status ("normal"/"impaired"/"failing"), notes (clinical '
        "explanation referencing specific values).\n\n"
        '7. "watchlist": Array of ONLY abnormal/borderline/concerning '
        "parameters. Each entry: parameter (name), current_value "
        '(string), unit, normal_range (string like "60-100"), status, '
        'trend, rate_of_change (e.g. "+3.2/hr"), clinical_concern (why '
        "this matters), recommended_action. Do NOT include stable, normal "
        "parameters.\n\n"
        '8. "risk_factors": Object with: infection_source_suspected '
        "(string describing likely source), immunocompromised (boolean), "
        "age_risk (boolean, true if age >65), comorbidity_burden "
        '("low"/"moderate"/"high"), contributing_factors (array of '
        "strings).\n\n"
        '9. "forecast_24h": Object with: expected_trajectory '
        '("improving"/"stable"/"deteriorating"/"critical"), narrative '
        "(3-5 sentences on predicted course), key_decision_points (array "
        "of objects with hour, trigger condition, recommended_response), "
        'intervention_urgency ("routine"/"urgent"/"emergent").\n\n'
        '10. "sepsis_probability_24h": Object with: probability (integer '
        '0-100, percentage), risk_level ("low"/"moderate"/"high"/'
        '"critical"), confidence ("low"/"moderate"/"high"), '
        "primary_drivers (array of strings), mitigating_factors (array of "
        "strings).\n\n"
        '11. "recommended_actions": Array of clinical actions. Each: '
        'priority ("immediate"/"within_1h"/"within_4h"/"routine"), '
        "action (specific instruction), rationale (why).\n\n"
        '12. "flags": Object of boolean clinical decision triggers: '
        "escalate_care, repeat_labs_needed, imaging_recommended, "
        "culture_recommended, antibiotic_consideration, "
        "fluid_resuscitation_needed, vasopressor_consideration, "
        "icu_transfer_recommended.\n\n"
        "OUTPUT FORMAT:\n"
        "- Return ONLY a valid JSON object matching the output schema "
        "below exactly.\n"
        "- No markdown, no code fences, no commentary, no text outside "
        "the JSON.\n\n"
        "--- CLINICAL RESEARCH CONTEXT ---\n"
        f"{context}\n\n"
        "--- OUTPUT SCHEMA (populate every field) ---\n"
        f"{schema}"
    )


def build_user_prompt(patient_data: Dict[str, Any]) -> str:
    """Construct the user prompt containing patient demographics and data.

    Args:
        patient_data: Parsed patient JSON with patient_info and hourly_data.

    Returns:
        Formatted user prompt string.
    """
    info = patient_data.get("patient_info", {})
    hourly_json = json.dumps(patient_data.get("hourly_data", []), indent=2)

    return (
        "PATIENT DEMOGRAPHICS:\n"
        f"- Name: {info.get('name', 'Unknown')}\n"
        f"- Age: {info.get('age', 'Unknown')}\n"
        f"- Gender: {info.get('gender', 'Unknown')}\n"
        f"- Weight: {info.get('weight_kg', 'Unknown')} kg\n"
        f"- Height: {info.get('height_cm', 'Unknown')} cm\n"
        f"- BMI: {info.get('bmi', 'Unknown')}\n"
        f"- Blood Type: {info.get('blood_type', 'Unknown')}\n"
        f"- Admission Reason: {info.get('admission_reason', 'Unknown')}\n"
        f"- Comorbidities: {_format_list(info.get('comorbidities'))}\n"
        f"- Allergies: {_format_list(info.get('allergies'))}\n\n"
        "COMPLETE HOURLY TIME-SERIES DATA (24 hours):\n"
        f"{hourly_json}\n\n"
        "INSTRUCTION: Set assessment_timestamp to the timestamp of the "
        "last data point in the hourly data above."
    )


def build_messages(
    context: str, schema: str, patient_data: Dict[str, Any]
) -> List[Dict[str, str]]:
    """Build complete message list for the OpenAI API call.

    Args:
        context: Clinical research context text.
        schema: JSON output schema text.
        patient_data: Parsed patient JSON.

    Returns:
        List of message dicts with role and content keys.
    """
    return [
        {"role": "system", "content": build_system_prompt(context, schema)},
        {"role": "user", "content": build_user_prompt(patient_data)},
    ]
