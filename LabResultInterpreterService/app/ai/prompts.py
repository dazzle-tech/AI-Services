"""Prompt templates for lab result interpretation."""
import json
from typing import Dict, Any, List, Optional


def get_system_prompt() -> str:
    """System prompt for lab interpretation - conservative, structured JSON output."""
    schema = {
        "severity": "low|moderate|high|critical",
        "key_findings": [
            {
                "lab_name": "string",
                "value": "string",
                "unit": "string|null",
                "reference_range": "string|null",
                "flag": "string|null",
                "timestamp": "string|null",
                "finding": "string",
            }
        ],
        "patterns": [
            {
                "label": "pattern_id",
                "reason": "cautious explanation grounded only in the provided data",
            }
        ],
        "trends": [
            {
                "lab_name": "string",
                "direction": "rising|falling|stable",
                "summary": "string",
                "from_value": "string|null",
                "to_value": "string|null",
                "from_timestamp": "string|null",
                "to_timestamp": "string|null",
                "unit": "string|null",
            }
        ],
        "follow_up_considerations": ["string"],
        "disclaimer": "This output is interpretation support and not a diagnosis.",
    }

    return f"""You are an expert clinical lab interpretation AI. Your role is to provide interpretation support only, not a diagnosis.

Return STRICT JSON only. No markdown, no code fences, and no extra text before or after the JSON object.

The output must be one JSON object with this exact top-level structure:
{json.dumps(schema, indent=2)}

Critical requirements:
1. Use cautious language such as "may suggest" or "compatible with". Never assert, confirm, or diagnose a condition.
2. Only use information present in the input. Do not hallucinate, infer hidden history, or add unsupported interpretations.
3. Never lose raw input data for any listed key finding or trend. Preserve the exact value, unit, reference_range, flag, and timestamp from the input whenever available.
4. key_findings must be an array of structured objects, never plain strings.
5. trends must include lab_name, direction, summary, from_value, to_value, from_timestamp, to_timestamp, and unit.
6. If a required field cannot be populated from the input, return null for that field instead of inventing content.
7. If there are no supported findings, patterns, or trends, return empty arrays.
8. Follow-up considerations must stay conservative and non-prescriptive.
9. Always include the disclaimer exactly as shown in the schema.
"""


def format_patient_context(patient_context: Optional[Dict[str, Any]]) -> str:
    """Format patient context for the prompt."""
    if not patient_context:
        return "None provided."
    parts = []
    if patient_context.get("patient_id"):
        parts.append(f"Patient ID: {patient_context['patient_id']}")
    if patient_context.get("age") is not None:
        parts.append(f"Age: {patient_context['age']} years")
    if patient_context.get("sex"):
        parts.append(f"Sex: {patient_context['sex']}")
    if patient_context.get("known_conditions"):
        parts.append("Known conditions: " + ", ".join(patient_context["known_conditions"]))
    if patient_context.get("medications"):
        parts.append("Medications: " + ", ".join(patient_context["medications"]))
    if patient_context.get("clinical_context"):
        parts.append("Clinical context: " + patient_context["clinical_context"])
    return "\n".join(parts) if parts else "None provided."


def format_lab_results(lab_results: List[Dict[str, Any]], label: str = "Current lab results") -> str:
    """Format lab results for the prompt."""
    if not lab_results:
        return f"{label}: None provided."
    lines = [f"{label}:"]
    for lab in lab_results:
        line = (
            f"  - {lab.get('name', 'N/A')}: {lab.get('value', 'N/A')} "
            f"{lab.get('unit', '') or ''} (ref: {lab.get('reference_range', 'N/A')}, "
            f"flag: {lab.get('flag', 'N/A')})"
        )
        if lab.get("timestamp"):
            line += f" @ {lab['timestamp']}"
        lines.append(line.strip())
    return "\n".join(lines)


def get_user_prompt(
    patient_context: Optional[Dict[str, Any]],
    lab_results: List[Dict[str, Any]],
    historical_lab_results: List[Dict[str, Any]],
) -> str:
    """Build user prompt with lab data and optional patient context."""
    patient_text = format_patient_context(patient_context)
    labs_text = format_lab_results(lab_results, "Current lab results")
    historical_text = format_lab_results(historical_lab_results, "Historical lab results (for trend analysis)")
    raw_payload = {
        "patient_context": patient_context,
        "lab_results": lab_results,
        "historical_lab_results": historical_lab_results,
    }

    return f"""Interpret the following lab results. Use patient context only if provided.

PATIENT CONTEXT (optional):
{patient_text}

{labs_text}

{historical_text}

RAW INPUT JSON (preserve exact raw values, units, reference ranges, flags, and timestamps):
{json.dumps(raw_payload, indent=2)}

Return ONLY a valid JSON object matching the required STRICT JSON schema. No markdown, no extra commentary."""


def build_lab_interpretation_prompt(
    patient_context: Optional[Dict[str, Any]],
    lab_results: List[Dict[str, Any]],
    historical_lab_results: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Build complete prompt structure for OpenAI API."""
    return [
        {"role": "system", "content": get_system_prompt()},
        {
            "role": "user",
            "content": get_user_prompt(patient_context, lab_results, historical_lab_results),
        },
    ]
