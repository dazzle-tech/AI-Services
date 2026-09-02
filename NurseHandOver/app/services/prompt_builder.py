"""
prompt_builder.py
-----------------
Responsible for constructing the prompts sent to GPT-4o.

Keeping prompt construction here means:
- Prompt tuning never touches gpt_service.py or the orchestrator.
- Each prompt can be unit-tested without making any API calls.
- The system prompt acts as an unchanging policy document; the user prompt
  is assembled fresh from each patient's data at generation time.
"""

from datetime import timezone
from typing import Optional

from app.models.schemas import Patient, PatientCurrentStatus
from app.services.chart_assembler import assemble_current_status, compact_vitals_from_readings


# ---------------------------------------------------------------------------
# System prompt — sent on every GPT call, defines all rules and output format
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """
You are a senior clinical documentation assistant supporting registered nurses \
during hospital shift handoffs in a general medicine ward.

Your sole task is to synthesize the structured patient chart data and the nurse's \
freeform shift notes provided to you into a clean, standardized SBAR handoff summary.

SBAR FORMAT:
- Situation:     Current clinical status in 1–3 sentences. Lead with the most urgent concern.
- Background:    Relevant history, admission reason, and key events this shift. Be specific.
- Assessment:    Your synthesis of the clinical picture based strictly on the data provided.
- Recommendation: A numbered list of specific, actionable tasks for the incoming nurse.

PRIORITY CLASSIFICATION — assign exactly one:
  critical : Any of — SpO2 < 92%, HR > 110 or < 50 bpm, Temp > 38.5 °C, RR > 22/min,
             systolic BP < 90 mmHg, pending urgent order not completed, unresolved active
             alert, or nurse note indicating acute deterioration.
  watch    : Borderline vitals, pending non-urgent orders, or nurse-noted concern without
             acute change.
  stable   : All vitals within acceptable range, no unresolved alerts, no nurse-flagged
             concerns, all time-critical medications administered.

FLAGS — extract a concise list of items requiring incoming nurse attention.
        Each flag must be a short phrase (e.g. "IV antibiotic dose pending",
        "Chest X-ray not yet performed"). Omit if nothing is outstanding.
        Always flag unresolved allergies and unresolved warnings.

STRICT RULES:
1. Output valid JSON only. No markdown, no preamble, no explanation outside the JSON.
2. Never infer or assume clinical details not present in the provided data.
3. If a field has no relevant information, write "Not documented this shift" — never guess.
4. Clinical language only. Write as a senior nurse communicating to a peer.
5. The Recommendation field must contain a numbered list of specific tasks, not generalities.
6. Reference timestamps from nurse notes where clinically relevant.
7. Every claim in Assessment must be traceable to a value in the input data.
8. Use only the latest vital-sign reading per type. Do not invent a trend from missing history.
9. Allergies, warnings, and pending procedures listed below are already filtered to current
   (unresolved / not completed) items — treat them as active.

OUTPUT FORMAT — return exactly this JSON structure and nothing else:
{
  "patient_id": "<string>",
  "priority": "<critical|watch|stable>",
  "situation": "<string>",
  "background": "<string>",
  "assessment": "<string>",
  "recommendation": "<string>",
  "flags": ["<string>", ...]
}
""".strip()


def get_system_prompt() -> str:
    """Returns the invariant system prompt."""
    return _SYSTEM_PROMPT


def build_user_prompt(
    patient: Patient,
    current_status: Optional[PatientCurrentStatus] = None,
) -> str:
    """
    Assembles a structured user prompt from a Patient object.
    This is the 'data injection' step — every field maps directly to chart data.
    Allergies/warnings/vitals/procedures are taken from the current-status snapshot.
    """
    status = current_status or assemble_current_status(patient)
    vitals = compact_vitals_from_readings(status.vital_signs) if status.vital_signs else patient.vitals

    def _val(value, unit: str = "") -> str:
        """Never present a missing value as 'None' — the model must not invent one."""
        return f"{value}{unit}" if value not in (None, "") else "not recorded"

    generated_at = status.generated_at
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    generated_stamp = generated_at.astimezone(timezone.utc).isoformat()

    # --- Medications ---
    if patient.medications:
        med_lines = "\n".join(
            f"  - {m.name} | Route: {_val(m.route)} | Due: {_val(m.due)} | Status: {_val(m.status)}"
            for m in patient.medications
        )
    else:
        med_lines = "  None documented."

    # --- Pending Orders ---
    if patient.pending_orders:
        order_lines = "\n".join(f"  - {o}" for o in patient.pending_orders)
    else:
        order_lines = "  None."

    # --- Pending OP / procedures ---
    if status.pending_procedures:
        procedure_lines = "\n".join(
            "  - "
            f"{p.name} | Status: {_val(p.status)} | Scheduled: {_val(p.scheduled_at)}"
            + (f" | {_val(p.notes)}" if p.notes else "")
            for p in status.pending_procedures
        )
    else:
        procedure_lines = "  None."

    # --- Unresolved allergies ---
    if status.allergies:
        allergy_lines = "\n".join(
            "  - "
            f"{a.name}"
            + (f" | Reaction: {a.reaction}" if a.reaction else "")
            + (f" | Status: {a.status}" if a.status else "")
            for a in status.allergies
        )
    else:
        allergy_lines = "  None."

    # --- Unresolved warnings ---
    if status.warnings:
        warning_lines = "\n".join(
            "  - "
            f"{w.text}"
            + (f" | Status: {w.status}" if w.status else "")
            for w in status.warnings
        )
    else:
        warning_lines = "  None."

    # --- Active Alerts ---
    if patient.alerts:
        alert_lines = "\n".join(f"  - {a}" for a in patient.alerts)
    else:
        alert_lines = "  None."

    # --- Latest vitals (per type) ---
    if status.vital_signs:
        vital_detail_lines = "\n".join(
            f"  - {v.type}: {v.value}"
            + (f" {v.unit}" if v.unit else "")
            + (f" (last: {v.recorded_at})" if v.recorded_at else "")
            for v in status.vital_signs
        )
    else:
        vital_detail_lines = "  None recorded."

    # --- Nurse Notes ---
    if patient.nurse_notes:
        note_lines = "\n".join(
            f"  [{n.time}] {n.text}" for n in patient.nurse_notes
        )
    else:
        note_lines = "  No notes recorded this shift."

    return f"""
Generate an SBAR handoff summary for the following patient.
Handover generated at: {generated_stamp}

--- PATIENT CHART ---
Patient ID      : {patient.patient_id}
Name            : {patient.name}
Age             : {_val(patient.age)}
Bed             : {_val(patient.bed)}
Diagnosis       : {_val(status.diagnosis)}
Past Medical Hx : {_val(status.past_medical_history)}
Hospital Course : {_val(status.hospital_course)}
Admission Date  : {_val(patient.admission_date)}

Vitals (latest reading per type; last recorded at {_val(vitals.last_updated)}):
  Heart Rate        : {_val(vitals.hr, " bpm")}
  Blood Pressure    : {_val(vitals.bp, " mmHg")}
  Temperature       : {_val(vitals.temp, " °C")}
  Respiratory Rate  : {_val(vitals.rr, " /min")}
  SpO2              : {_val(vitals.spo2, " %")}

Latest vital signs:
{vital_detail_lines}

Unresolved allergies:
{allergy_lines}

Unresolved warnings:
{warning_lines}

Active Medications:
{med_lines}

Pending Orders:
{order_lines}

Pending OP / procedures:
{procedure_lines}

Active Alerts:
{alert_lines}

--- NURSE NOTES (this shift, chronological) ---
{note_lines}

--- INSTRUCTION ---
Return only the JSON object described in your system instructions. No other text.
""".strip()
