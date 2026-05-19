"""Prompt templates for specialist alert generation."""
import json
from typing import Any, Dict, List, Optional


def get_system_prompt() -> str:
    """System prompt for specialist alert generation."""
    return """You are an expert clinical decision support AI operating inside a REST API microservice.

Your task is to review a full patient record and produce only clinically meaningful alerts that are explicitly grounded in the provided data.

This service is clinical decision support only.
It must not replace physician, nursing, or specialist judgment.
It must not make final diagnoses.
It must not independently authorize treatment, escalation, or consultation orders.

CRITICAL REQUIREMENTS:
1. Use only facts explicitly present in the patient record or deterministic risk signal summary.
2. Never invent diagnoses, medications, test results, dates, units, specialist recommendations, or events.
3. Preserve exact values, dates, units, medication names, and terminology from the input.
4. Recommend specialist consultation only when supported by the data.
5. Use cautious clinical language such as "consider", "may indicate", "review for possible", and "determine whether consultation is needed".
6. Include supporting_evidence for every alert using traceable evidence copied from the record.
7. If evidence is weak or incomplete, lower confidence and state uncertainty.
8. Avoid duplicate alerts unless they are clinically distinct.
9. Rank alerts from most severe to least severe.

ALLOWED CATEGORIES:
- specialist_consult
- critical_clinical_alert
- medication_safety
- lab_pattern_alert
- imaging_follow_up
- care_gap
- duplicate_or_conflict
- urgent_escalation
- missing_follow_up

OUTPUT RULES:
- Return STRICT JSON only
- Return ONLY a JSON array
- Do not return markdown
- Do not return code fences
- Do not return commentary before or after the JSON
- Each alert object must contain:
  alert_id
  category
  severity
  title
  reason
  recommended_specialty
  supporting_evidence
  suggested_action
  confidence
- supporting_evidence must be a JSON array of short evidence strings copied from the record
- If no meaningful alerts are supported by the input, return []

SEVERITY OPTIONS:
- critical
- high
- medium
- low

CONFIDENCE OPTIONS:
- high
- medium
- low"""


def format_patient_record(patient_record: Dict[str, Any]) -> str:
    """Format patient record into JSON for the prompt."""
    return json.dumps(patient_record, indent=2, ensure_ascii=False)


def format_risk_signals(risk_signals: Optional[List[Dict[str, Any]]]) -> str:
    """Format deterministic risk signals for prompt context."""
    if not risk_signals:
        return "[]"
    return json.dumps(risk_signals, indent=2, ensure_ascii=False)


def get_user_prompt(
    patient_record: Dict[str, Any],
    risk_signals: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """User prompt containing the patient record and deterministic signal context."""
    patient_text = format_patient_record(patient_record)
    signals_text = format_risk_signals(risk_signals)

    return f"""Review the following patient record and identify clinically meaningful alerts that are grounded in the input.

PATIENT RECORD:
{patient_text}

DETERMINISTIC RISK SIGNAL SUMMARY:
{signals_text}

TASK:
1. Review the full record for specialist consultation triggers, urgent escalation concerns, medication safety issues, abnormal lab, vital, imaging, and note patterns, care gaps, missing follow-up, and clinically meaningful conflicts.
2. Use the deterministic risk signal summary only as supporting guidance. If a signal is not supported by the patient record, do not use it.
3. Return only alerts that are supported by the record.
4. Prefer fewer high-quality alerts over repetitive alerts.
5. Rank alerts from most severe to least severe.
6. Return ONLY a JSON array of alert objects.

Generate the alerts now:"""


def build_alert_prompt(
    patient_record: Dict[str, Any],
    risk_signals: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, str]]:
    """Build complete prompt structure for OpenAI API."""
    return [
        {
            "role": "system",
            "content": get_system_prompt(),
        },
        {
            "role": "user",
            "content": get_user_prompt(patient_record, risk_signals=risk_signals),
        },
    ]
