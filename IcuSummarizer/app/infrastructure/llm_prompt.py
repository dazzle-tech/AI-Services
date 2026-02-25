"""LLM prompt construction"""
import json
from datetime import datetime
from typing import Dict, Any
from app.domain.clinical_models import ClinicalSummary


# JSON Schema for structured note output
# Note: OpenAI structured outputs require additionalProperties: false for all objects
NOTE_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "one_liner": {
            "type": "string",
            "description": "One-line summary of patient status"
        },
        "overnight_events": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of significant overnight events"
        },
        "objective_trends": {
            "type": "object",
            "description": "Objective trends summary",
            "additionalProperties": False,
            "properties": {}
        },
        "problem_list": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "problem": {"type": "string"},
                    "assessment": {"type": "string"},
                    "plan": {"type": "string"}
                },
                "required": ["problem", "assessment", "plan"]
            },
            "description": "Problem list with assessment and plan"
        },
        "lines_tubes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of lines, tubes, and devices"
        },
        "prophylaxis": {
            "type": "string",
            "description": "Prophylaxis information"
        },
        "nutrition": {
            "type": "string",
            "description": "Nutrition status"
        },
        "code_status": {
            "type": "string",
            "description": "Code status"
        },
        "todo": {
            "type": "array",
            "items": {"type": "string"},
            "description": "To-do items for the day"
        },
        "watchouts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Things to watch out for"
        }
    },
    "required": [
        "one_liner",
        "overnight_events",
        "objective_trends",
        "problem_list",
        "lines_tubes",
        "prophylaxis",
        "nutrition",
        "code_status",
        "todo",
        "watchouts"
    ]
}


def build_summary_prompt(clinical_summary: ClinicalSummary) -> str:
    """
    Build prompt for generating ICU daily summary.
    
    The LLM only sees ClinicalSummary JSON, not raw flowsheet data.
    """
    # Convert clinical summary to JSON for prompt
    summary_dict = clinical_summary.model_dump(mode='json', exclude_none=True)
    summary_json = json.dumps(summary_dict, indent=2, default=str)
    
    prompt = f"""You are generating an ICU daily summary note based on structured clinical data.

CRITICAL RULES:
1. NEVER invent or fabricate data. If information is missing, use "Not available" or null.
2. Base your summary ONLY on the provided ClinicalSummary data.
3. Be concise and clinically relevant.
4. Focus on actionable information.

CLINICAL SUMMARY DATA:
{summary_json}

TIME WINDOW:
Start: {clinical_summary.time_window_start.isoformat()}
End: {clinical_summary.time_window_end.isoformat()}

Generate a comprehensive ICU daily summary note in markdown format. Include:
- Patient overview
- Overnight events
- Vital signs trends
- Active infusions
- I/O status
- Recent labs
- Problem list with assessment and plan
- Lines and tubes
- Prophylaxis and nutrition
- Code status
- To-do items
- Watchouts

Be professional, concise, and clinically accurate."""
    
    return prompt


def build_structured_note_prompt(clinical_summary: ClinicalSummary) -> str:
    """
    Build prompt for generating structured JSON note.
    """
    summary_dict = clinical_summary.model_dump(mode='json', exclude_none=True)
    summary_json = json.dumps(summary_dict, indent=2, default=str)
    
    prompt = f"""You are generating a structured ICU daily summary in JSON format.

CRITICAL RULES:
1. NEVER invent or fabricate data. If information is missing, use "Not available" or null.
2. Base your output ONLY on the provided ClinicalSummary data.
3. All arrays should be non-null (use empty arrays if no data).

CLINICAL SUMMARY DATA:
{summary_json}

TIME WINDOW:
Start: {clinical_summary.time_window_start.isoformat()}
End: {clinical_summary.time_window_end.isoformat()}

Generate the structured summary JSON following the exact schema provided.
For problem_list, create problems based on the clinical data (e.g., respiratory failure, shock, AKI).
For objective_trends, summarize key vital sign trends and notable changes.
For overnight_events, extract from recent_events if available.

If data is missing for any field, use appropriate defaults:
- Empty arrays for list fields
- "Not available" for string fields when data is truly missing
- null only when explicitly allowed by schema"""
    
    return prompt
