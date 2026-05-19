"""Prompt templates for discharge planning assessment."""
import json
from typing import Dict, Any, List


def get_system_prompt() -> str:
    """System prompt for discharge planning assessment."""
    return """You are an expert discharge planning AI that supports clinicians with discharge readiness assessment. Your role is to ANALYZE and SUPPORT—never to authorize or make final discharge decisions.

TASK:
Assess discharge readiness based on provided clinical and operational data. Return a structured JSON object with:
- readiness_status: one of "ready", "needs_review", "not_ready", or "unclear"
- readiness_reason: brief explanation
- blockers: array of {category, title, reason} for each identified blocker
- medication_reconciliation_concerns: array of strings
- follow_up_considerations: array of strings
- draft_discharge_summary: narrative paragraph
- disclaimer: "This output supports discharge planning and does not replace clinician judgment."

CRITICAL REQUIREMENTS:
1. FIDELITY: Use ONLY information from the input. Never invent facts, medications, problems, or tasks.
2. CONSERVATIVE: When data is incomplete or ambiguous, use "needs_review" or "unclear"—never claim a patient is definitively safe for discharge unless explicitly supported.
3. NO AUTHORIZATION: Never state that a patient is "safe for discharge" or "cleared for discharge." Use language like "may be appropriate" or "supports consideration."
4. PRESERVE: Keep exact medication names, problems, and operational details as provided.
5. BLOCKERS: Identify blockers across: pending_test, follow_up, patient_education, equipment, medication, logistics, clinical.
6. OUTPUT FORMAT: Return STRICT JSON only. No markdown code blocks, no extra commentary, no text outside the JSON object."""


def format_discharge_input(data: Dict[str, Any]) -> str:
    """Format discharge planning input into structured text."""
    parts = []
    
    ctx = data.get("patient_context", {})
    if ctx:
        parts.append("PATIENT CONTEXT:")
        parts.append(f"  Patient ID: {ctx.get('patient_id', 'N/A')}")
        parts.append(f"  Admission: {ctx.get('admission_date', 'N/A')}")
        parts.append(f"  Primary Diagnosis: {ctx.get('primary_diagnosis', 'N/A')}")
        if ctx.get("secondary_diagnoses"):
            parts.append(f"  Secondary: {', '.join(ctx['secondary_diagnoses'])}")
        parts.append(f"  Status: {ctx.get('current_status', 'N/A')}")
    
    clinical = data.get("clinical_data", {})
    if clinical:
        parts.append("\nCLINICAL DATA:")
        vitals = clinical.get("latest_vitals", [])
        if vitals:
            vitals_str = ", ".join([f"{v.get('name', '')} {v.get('value', '')}{v.get('unit', '')}" for v in vitals])
            parts.append(f"  Vitals: {vitals_str}")
        pending = clinical.get("pending_tests", [])
        if pending:
            parts.append(f"  Pending tests: {json.dumps(pending)}")
        if clinical.get("active_problems"):
            parts.append(f"  Active problems: {', '.join(clinical['active_problems'])}")
        if clinical.get("medications_current"):
            parts.append(f"  Current medications: {', '.join(clinical['medications_current'])}")
        if clinical.get("medications_planned_for_discharge"):
            parts.append(f"  Planned for discharge: {', '.join(clinical['medications_planned_for_discharge'])}")
        notes = clinical.get("notes", [])
        if notes:
            for n in notes:
                text = n.get("text", "") or ""
                excerpt = (text[:200] + "..." if len(text) > 200 else text)
                parts.append(f"  Note [{n.get('type', '')}]: {excerpt}")
    
    op = data.get("operational_data", {})
    if op:
        parts.append("\nOPERATIONAL DATA:")
        if op.get("follow_up_appointments"):
            parts.append(f"  Follow-up: {json.dumps(op['follow_up_appointments'])}")
        if op.get("patient_education"):
            parts.append(f"  Education: {json.dumps(op['patient_education'])}")
        if op.get("transport_status"):
            parts.append(f"  Transport: {op['transport_status']}")
        if op.get("home_support"):
            parts.append(f"  Home support: {op['home_support']}")
        if op.get("equipment_needs"):
            parts.append(f"  Equipment: {json.dumps(op['equipment_needs'])}")
    
    return "\n".join(parts)


def get_user_prompt(data: Dict[str, Any]) -> str:
    """Build user prompt with discharge planning input."""
    formatted = format_discharge_input(data)
    
    return f"""Analyze the following discharge-related data and return a JSON object with the discharge plan.

{formatted}

INSTRUCTIONS:
1. Assess discharge readiness conservatively.
2. Identify all blockers from the data provided—do not invent any.
3. Compare medications_current vs medications_planned_for_discharge and note any reconciliation concerns.
4. List follow-up considerations based only on the input.
5. Write a draft_discharge_summary paragraph (2-4 sentences) summarizing the assessment.
6. Include the exact disclaimer: "This output supports discharge planning and does not replace clinician judgment."

Return ONLY a valid JSON object with keys: readiness_status, readiness_reason, blockers, medication_reconciliation_concerns, follow_up_considerations, draft_discharge_summary, disclaimer.
No markdown. No commentary."""


def build_discharge_prompt(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build complete prompt structure for OpenAI API."""
    return [
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": get_user_prompt(data)}
    ]
