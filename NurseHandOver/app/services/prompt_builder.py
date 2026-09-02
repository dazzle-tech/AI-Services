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

from app.models.schemas import Patient


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

STRICT RULES:
1. Output valid JSON only. No markdown, no preamble, no explanation outside the JSON.
2. Never infer or assume clinical details not present in the provided data.
3. If a field has no relevant information, write "Not documented this shift" — never guess.
4. Clinical language only. Write as a senior nurse communicating to a peer.
5. The Recommendation field must contain a numbered list of specific tasks, not generalities.
6. Reference timestamps from nurse notes where clinically relevant.
7. Every claim in Assessment must be traceable to a value in the input data.

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


def build_user_prompt(patient: Patient) -> str:
    """
    Assembles a structured user prompt from a Patient object.
    This is the 'data injection' step — every field maps directly to chart data.
    """
    def _val(value, unit: str = "") -> str:
        """Never present a missing value as 'None' — the model must not invent one."""
        return f"{value}{unit}" if value not in (None, "") else "not recorded"

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

    # --- Active Alerts ---
    if patient.alerts:
        alert_lines = "\n".join(f"  - {a}" for a in patient.alerts)
    else:
        alert_lines = "  None."

    # --- Nurse Notes ---
    if patient.nurse_notes:
        note_lines = "\n".join(
            f"  [{n.time}] {n.text}" for n in patient.nurse_notes
        )
    else:
        note_lines = "  No notes recorded this shift."

    return f"""
Generate an SBAR handoff summary for the following patient.

--- PATIENT CHART ---
Patient ID      : {patient.patient_id}
Name            : {patient.name}
Age             : {_val(patient.age)}
Bed             : {_val(patient.bed)}
Diagnosis       : {_val(patient.diagnosis)}
Admission Date  : {_val(patient.admission_date)}

Vitals (last recorded at {_val(patient.vitals.last_updated)}):
  Heart Rate        : {_val(patient.vitals.hr, " bpm")}
  Blood Pressure    : {_val(patient.vitals.bp, " mmHg")}
  Temperature       : {_val(patient.vitals.temp, " °C")}
  Respiratory Rate  : {_val(patient.vitals.rr, " /min")}
  SpO2              : {_val(patient.vitals.spo2, " %")}

Active Medications:
{med_lines}

Pending Orders:
{order_lines}

Active Alerts:
{alert_lines}

--- NURSE NOTES (this shift, chronological) ---
{note_lines}

--- INSTRUCTION ---
Return only the JSON object described in your system instructions. No other text.
""".strip()
