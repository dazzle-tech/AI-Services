"""Prompt templates for patient timeline generation."""
import json
from typing import Any, Dict, List


def get_system_prompt() -> str:
    """System prompt for patient timeline generation."""
    return """You are an expert clinical timeline extraction AI.

Your task is to extract clinically important patient events from structured and semi-structured medical data and convert them into a chronological timeline.

CRITICAL REQUIREMENTS:
1. FIDELITY: Use only information explicitly present in the input. Never invent or infer missing facts.
2. CLINICAL PRECISION: Preserve medical terminology, drug names, abbreviations, values, units, dates, and numbers exactly as provided.
3. TRACEABILITY: Every event must include the input source field that supports it.
4. DEDUPLICATION: Merge obvious duplicate events if the same event appears in multiple places.
5. CHRONOLOGY: Output events in date ascending order whenever dates are available.
6. JSON ONLY: Return only a strict JSON array. Do not return markdown, explanations, headings, or code fences.

Each timeline event must use this exact schema:
{
  "date": "ISO date string or source-provided date string",
  "event_type": "diagnosis | medication | admission | procedure | lab | allergy | symptom | vital",
  "title": "Short event title",
  "description": "Concise factual description grounded in the input",
  "clinical_importance": "high | medium | low",
  "source": "diagnoses | medications | lab_results | vitals | procedures | encounters | notes | allergies"
}

EVENT SELECTION RULES:
- Include clinically important diagnoses, medication starts/stops/changes, admissions, procedures, abnormal or clinically relevant labs, allergies, vital abnormalities or notable measurements, and symptoms documented in notes.
- Use event_type "admission" for admissions and hospital encounters.
- Use event_type "vital" for notable vital-sign events from the vitals source.
- Only include symptoms from notes or encounter reasons if they are explicitly stated.
- Do not include null facts, empty values, or unsupported interpretations.
- Return an empty JSON array [] if no timeline-worthy events are present."""


def format_patient_data(patient_data: Dict[str, Any]) -> str:
    """Format patient data into JSON for the prompt."""
    return json.dumps(patient_data, indent=2, ensure_ascii=True)


def get_user_prompt(patient_data: Dict[str, Any]) -> str:
    """User prompt containing patient data."""
    patient_text = format_patient_data(patient_data)

    return f"""Extract a patient timeline from the following medical data.

PATIENT DATA:
{patient_text}

INSTRUCTIONS:
1. Extract clinically important events only.
2. Merge duplicates when they refer to the same event.
3. Preserve exact dates, terminology, and numeric values.
4. Return STRICT JSON.
5. Return only a JSON array of events with no surrounding commentary."""


def build_timeline_prompt(patient_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build complete prompt structure for OpenAI API."""
    return [
        {
            "role": "system",
            "content": get_system_prompt()
        },
        {
            "role": "user",
            "content": get_user_prompt(patient_data)
        }
    ]
