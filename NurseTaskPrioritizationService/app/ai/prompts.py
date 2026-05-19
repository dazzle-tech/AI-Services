"""Prompt templates for nursing task prioritization."""
import json
from typing import Dict, Any, List


def get_system_prompt() -> str:
    """System prompt for task prioritization."""
    return """You are an expert clinical decision-support AI specialized in nursing task prioritization.

Your task is to analyze patient monitoring data, pending nursing tasks, medication schedules, abnormal findings, and operational context, then return a prioritized nursing task list ordered by urgency and clinical importance.

CRITICAL REQUIREMENTS:
1. ONLY use information explicitly provided in the input - never invent, infer, or assume facts not present
2. Preserve exact values, timestamps, units, and medical terms from the input
3. Return STRICT JSON - no markdown, no code blocks, no extra commentary
4. Return ONLY a JSON array of prioritized tasks - nothing else
5. Rank tasks from most urgent (rank 1) to least urgent
6. Combine clinical urgency (vitals, labs, risk flags) with operational urgency (due times, time-sensitive medications)
7. Do not duplicate similar tasks unnecessarily
8. When data is insufficient or conflicting, be conservative and mention uncertainty in the reason field
9. Include source_signals that trace back to specific input data (exact values, timestamps, notes)
10. Do not issue definitive treatment decisions - this supports prioritization only, not nursing judgment replacement

OUTPUT FORMAT - Return a JSON array where each element has:
- rank: integer (1 = most urgent)
- patient_id: string
- room: string
- task_id: string
- task_type: string (e.g., clinical_reassessment, medication, fall_prevention, lab_followup)
- title: string
- reason: string (concise clinical rationale, preserve exact values)
- urgency: string (critical | high | medium | low)
- recommended_timeframe: string (e.g., immediate | within_10_minutes | within_30_minutes)
- source_signals: array of strings (traceable to input, e.g., "oxygen_saturation=88%", "heart_rate=118 bpm")"""


def format_patient_data(request_data: Dict[str, Any]) -> str:
    """Format request data into structured text for the prompt."""
    lines = []

    unit = request_data.get("unit_context", {})
    nurse = request_data.get("nurse_context", {})
    lines.append(f"UNIT: {unit.get('unit_name', 'N/A')} | Shift: {unit.get('shift', 'N/A')} | Generated: {unit.get('generated_at', 'N/A')}")
    lines.append(f"NURSE: {nurse.get('nurse_id', 'N/A')} | Assigned rooms: {', '.join(nurse.get('assigned_rooms', []))}")
    lines.append("")

    for p in request_data.get("patients", []):
        lines.append(f"--- PATIENT {p.get('patient_id', 'N/A')} (Room {p.get('room', 'N/A')}) ---")
        if p.get("patient_risk_flags"):
            lines.append(f"Risk flags: {', '.join(p['patient_risk_flags'])}")

        if p.get("vitals"):
            lines.append("Vitals:")
            for v in p["vitals"]:
                lines.append(f"  - {v.get('name', '')}: {v.get('value', '')} {v.get('unit', '')} @ {v.get('timestamp', '')}")

        if p.get("lab_alerts"):
            lines.append("Lab alerts:")
            for l in p["lab_alerts"]:
                lines.append(f"  - {l.get('name', '')}: {l.get('value', '')} {l.get('unit', '')} [{l.get('flag', '')}] @ {l.get('timestamp', '')}")

        if p.get("medication_tasks"):
            lines.append("Medication tasks:")
            for m in p["medication_tasks"]:
                hint = f" [{m.get('priority_hint', '')}]" if m.get("priority_hint") else ""
                lines.append(f"  - {m.get('task_id', '')}: {m.get('medication_name', '')} due {m.get('due_time', '')} status={m.get('status', '')}{hint}")

        if p.get("nursing_tasks"):
            lines.append("Nursing tasks:")
            for t in p["nursing_tasks"]:
                lines.append(f"  - {t.get('task_id', '')}: {t.get('title', '')} due {t.get('due_time', '')} status={t.get('status', '')}")

        if p.get("notes"):
            lines.append("Notes:")
            for n in p["notes"]:
                lines.append(f"  - [{n.get('type', '')}] {n.get('timestamp', '')}: {n.get('text', '')}")

        lines.append("")

    return "\n".join(lines).strip()


def get_user_prompt(request_data: Dict[str, Any]) -> str:
    """User prompt containing formatted request data."""
    data_text = format_patient_data(request_data)

    return f"""Prioritize the nursing tasks below based only on the provided data.

INPUT DATA:
{data_text}

INSTRUCTIONS:
1. Rank ALL tasks across all patients by clinical and operational urgency
2. Consider: vital instability, abnormal labs, due medications, overdue tasks, patient risk flags
3. Return ONLY a JSON array of prioritized task objects - no other text
4. Each object must have: rank, patient_id, room, task_id, task_type, title, reason, urgency, recommended_timeframe, source_signals
5. Use exact values from the input in reason and source_signals
6. Do not add tasks or facts not present in the input

Return the JSON array now:"""


def build_prioritization_prompt(request_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build complete prompt structure for OpenAI API."""
    return [
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": get_user_prompt(request_data)}
    ]
