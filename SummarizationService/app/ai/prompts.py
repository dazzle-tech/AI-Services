"""Prompt templates for clinical summary generation."""
import json
from typing import Any, Dict, List, Optional

from app.core.config import settings


def _uses_qwen3_thinking_model() -> bool:
    """
    Qwen3-family models (served locally via Ollama in this setup) think by
    default: they emit a <think>...</think> reasoning block before the
    actual answer, and those reasoning tokens count against max_tokens. With
    a low max_tokens budget the model can burn the whole budget "thinking"
    and return an empty content field. Appending "/no_think" to the prompt
    is the documented way to disable this for Qwen3. This should only be
    applied for Qwen3 models - it would just be inert clutter in a prompt
    sent to a non-Qwen provider (e.g. real GPT-4/GPT-4o).
    """
    model_name = (settings.openai_model or "").lower()
    return "qwen3" in model_name or "qwen" in model_name


def get_system_prompt() -> str:
    """System prompt optimized for GPT-4o clinical summary generation."""
    return """You are an expert medical documentation AI specialized in creating concise, coherent clinical summary paragraphs using GPT-4.

Your task is to transform structured patient data into a single, well-written clinical summary paragraph that:
- Reads naturally and professionally
- Preserves all medical terminology, abbreviations, and values exactly as provided
- Maintains clinical accuracy and completeness
- Flows logically from patient demographics through clinical findings

CRITICAL REQUIREMENTS:
1. FIDELITY (MOST IMPORTANT RULE): ONLY use information explicitly present in the PATIENT DATA below.
   - Never invent, infer, guess, or "fill in" typical/plausible values for a condition (no invented drug names, dosages, lab values, vital signs, or symptoms).
   - If a category (symptoms, medications, vitals, labs, allergies, etc.) is not present in PATIENT DATA, do NOT mention it at all - do not say "no known allergies" or similar unless that was explicitly stated in the input.
   - Every number, unit, and named entity in your output MUST appear, in some form, in PATIENT DATA. If you are not sure a detail was given, leave it out.
2. PRECISION: Preserve exact medical abbreviations (e.g., "BID", "PRN", "STEMI"), numbers, units, and terminology exactly as given - do not convert, calculate, or estimate new values.
3. STRUCTURE: Create ONE coherent paragraph that flows naturally.
4. LANGUAGE: Use professional medical documentation style - clear, concise, objective.
5. LENGTH: The summary should be as long as the available data supports and no longer. Sparse input (e.g., only age/gender/diagnosis) should produce a short 1-2 sentence summary. Do not pad the summary with generic or invented clinical detail to reach a target length.

OUTPUT FORMAT:
- Return ONLY the clinical summary text - no labels, headers, or meta-commentary
- Start directly with patient description (e.g., "A 45-year-old male...")
- End with a complete sentence - no trailing fragments"""


def format_patient_data(patient_data: Dict[str, Any]) -> str:
    """Format patient data into a structured text for the prompt."""
    # Use age exactly as provided (no calculation / conversion)
    raw_age = patient_data.get("Age", "N/A")
    age_text = str(raw_age) if raw_age is not None else "N/A"
    
    gender = patient_data.get("Gender", "N/A")
    diagnosis = patient_data.get("Diagnosis", "N/A")
    
    # First sentence uses the raw strings
    parts = [f"A {age_text} {gender} with {diagnosis}"]
    
    if patient_data.get("Symptoms"):
        parts.append("Symptoms: " + ", ".join(patient_data["Symptoms"]))
    if patient_data.get("Medications"):
        parts.append("Medications: " + ", ".join(patient_data["Medications"]))
    if patient_data.get("Surgeries"):
        surgery_parts = [f"{s['name']} ({s['status']})" for s in patient_data["Surgeries"]]
        parts.append("Surgeries: " + ", ".join(surgery_parts))
    if patient_data.get("Allergies"):
        parts.append("Allergies: " + ", ".join(patient_data["Allergies"]))
    if patient_data.get("Medical_Warnings"):
        parts.append("Medical warnings: " + ", ".join(patient_data["Medical_Warnings"]))
    if patient_data.get("Problems"):
        parts.append("Comorbidities: " + ", ".join(patient_data["Problems"]))
    if patient_data.get("Vitals"):
        vitals = patient_data["Vitals"]
        vitals_text = ", ".join([f"{k} {v}" for k, v in vitals.items()])
        parts.append("Vital signs: " + vitals_text)
    if patient_data.get("Lab_Results"):
        parts.append("Lab results: " + json.dumps(patient_data["Lab_Results"], indent=2))
    
    return ". ".join(parts)


def get_user_prompt(patient_data: Dict[str, Any]) -> str:
    """User prompt containing formatted patient data - optimized for GPT-4."""
    patient_text = format_patient_data(patient_data)
    
    prompt = f"""Transform the following structured patient data into a single, coherent clinical summary paragraph.

PATIENT DATA:
{patient_text}

INSTRUCTIONS:
1. Synthesize only the information shown above into one flowing paragraph
2. Start with patient demographics (age, gender) and primary diagnosis
3. Integrate symptoms, medications, allergies, and other clinical details naturally - but only if they appear above
4. Include vital signs and lab results only if they appear above, formatted appropriately
5. Maintain exact medical terminology, abbreviations, and values as given - do not add, estimate, or infer new ones
6. If the data above is limited to demographics and diagnosis, write a brief 1-2 sentence summary and stop - do not invent additional clinical detail to make the summary longer

Generate the clinical summary now:"""

    if _uses_qwen3_thinking_model():
        prompt += "\n\n/no_think"

    return prompt


def build_summary_prompt(patient_data: Dict[str, Any]) -> List[Dict[str, str]]:
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


def get_encounter_system_prompt() -> str:
    """System prompt for encounter clinical-overview summaries."""
    return """You are an expert clinical documentation AI that writes encounter summaries for clinicians.

Your task is to synthesize structured encounter chart data into a clear clinical overview that:
- Reflects the hospital course chronologically when notes support it
- Integrates diagnoses, medications, allergies, warnings, vitals, and order results when present
- Flags deterioration trends and pending/rejected investigations when asked or when evident in the data
- Uses professional medical documentation style

CRITICAL REQUIREMENTS:
1. FIDELITY: Only use information present in ENCOUNTER DATA. Never invent diagnoses, drugs, labs, vitals, or events.
2. PRECISION: Keep codes, drug names, doses, units, dates, and abnormal flags exactly as given.
3. Do not invent pending work unless the source data indicates it (e.g. rejected sample, explicit plan, awaiting result).
4. Respect detail_level and any EXTRA INSTRUCTIONS from the request.
5. Return ONLY the summary text — no titles, JSON, or meta-commentary."""


def format_encounter_data(encounter_data: Dict[str, Any]) -> str:
    """Format encounter_data into readable prompt sections."""
    sections: List[str] = []

    for key, label in (
        ("physician_notes", "Physician notes"),
        ("nurse_notes", "Nurse notes"),
        ("hospital_course_notes", "Hospital course notes"),
    ):
        notes = encounter_data.get(key) or []
        if notes:
            bullets = "\n".join(f"- {n}" for n in notes if n)
            sections.append(f"{label}:\n{bullets}")

    diagnoses = encounter_data.get("diagnosis") or []
    if diagnoses:
        lines = []
        for d in diagnoses:
            dtype = d.get("diagnosis_type") or ""
            code = d.get("diagnosis_code") or ""
            desc = d.get("diagnosis_description") or ""
            lines.append(f"- [{dtype}] {code} {desc}".strip())
        sections.append("Diagnoses:\n" + "\n".join(lines))

    meds = encounter_data.get("medications") or []
    if meds:
        lines = []
        for m in meds:
            parts = [
                m.get("drug_name") or m.get("scientific_name") or "Unknown drug",
                f"{m.get('dose') or ''} {m.get('dose_unit') or ''}".strip(),
                m.get("route") or "",
                m.get("frequency") or "",
                m.get("duration") or "",
                f"status={m.get('status')}" if m.get("status") else "",
                "STAT" if m.get("is_stat") else "",
                f"start={m.get('start_date')}" if m.get("start_date") else "",
                f"end={m.get('end_date')}" if m.get("end_date") else "",
            ]
            lines.append("- " + " | ".join(p for p in parts if p))
        sections.append("Medications:\n" + "\n".join(lines))

    allergies = encounter_data.get("allergies") or []
    if allergies:
        lines = []
        for a in allergies:
            note = f" ({a.get('note')})" if a.get("note") else ""
            lines.append(
                f"- {a.get('allergy_description')} [{a.get('allergy_type_description')}]{note}"
            )
        sections.append("Allergies:\n" + "\n".join(lines))

    warnings = encounter_data.get("warnings") or []
    if warnings:
        lines = []
        for w in warnings:
            resolved = "resolved" if w.get("resolved") else "active"
            lines.append(
                f"- {w.get('warning_description')} [{w.get('warning_type')}] ({resolved})"
            )
        sections.append("Warnings:\n" + "\n".join(lines))

    results = encounter_data.get("order_results") or []
    if results:
        lines = []
        for r in results:
            rejected = " REJECTED" if r.get("is_sample_rejected") else ""
            value = r.get("result_value")
            unit = r.get("unit") or ""
            flag = r.get("abnormal_flag")
            notes = r.get("result_notes") or ""
            value_text = f"{value} {unit}".strip() if value not in (None, "") else "n/a"
            flag_text = f" flag={flag}" if flag else ""
            lines.append(
                f"- [{r.get('order_type')}] {r.get('profile_name')} / {r.get('result_name')}: "
                f"{value_text}{flag_text}{rejected}"
                + (f"; {notes}" if notes else "")
                + (f" ({r.get('result_date')})" if r.get("result_date") else "")
            )
        sections.append("Order results:\n" + "\n".join(lines))

    vitals = encounter_data.get("vital_signs") or {}
    if vitals:
        pairs = [f"{k}={v}" for k, v in vitals.items() if v not in (None, "")]
        if pairs:
            sections.append("Vital signs: " + ", ".join(pairs))

    return "\n\n".join(sections) if sections else "(no encounter data provided)"


def get_encounter_user_prompt(
    *,
    context_type: str,
    purpose: str,
    detail_level: str,
    encounter_id: str,
    extra_prompt: Optional[str],
    encounter_data: Dict[str, Any],
) -> str:
    """User prompt for encounter summary generation."""
    data_text = format_encounter_data(encounter_data)
    extra = (extra_prompt or "").strip()
    extra_block = f"\nEXTRA INSTRUCTIONS:\n{extra}\n" if extra else "\n"

    prompt = f"""Write a clinical encounter summary for the request below.

CONTEXT:
- context_type: {context_type}
- purpose: {purpose}
- detail_level: {detail_level}
- encounter_id: {encounter_id}
{extra_block}
ENCOUNTER DATA:
{data_text}

INSTRUCTIONS:
1. Produce a {detail_level} clinical overview suitable for {purpose}
2. Use only facts from ENCOUNTER DATA
3. Call out deterioration trends only if supported by the notes/results; otherwise state improvement/stability when supported
4. Explicitly mention pending or failed investigations when present (e.g. rejected samples, awaiting input)
5. Return only the summary prose
"""

    if _uses_qwen3_thinking_model():
        prompt += "\n\n/no_think"

    return prompt


def build_encounter_summary_prompt(
    *,
    context_type: str,
    purpose: str,
    detail_level: str,
    encounter_id: str,
    extra_prompt: Optional[str],
    encounter_data: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Build OpenAI chat messages for encounter summary."""
    return [
        {"role": "system", "content": get_encounter_system_prompt()},
        {
            "role": "user",
            "content": get_encounter_user_prompt(
                context_type=context_type,
                purpose=purpose,
                detail_level=detail_level,
                encounter_id=encounter_id,
                extra_prompt=extra_prompt,
                encounter_data=encounter_data,
            ),
        },
    ]

