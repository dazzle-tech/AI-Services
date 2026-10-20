"""
unified_prompts.py

A single, adaptive prompt-building module intended to be shared by both
ORScribe and ConvoScribe. Instead of each service hardcoding a fixed system
prompt per task (role identification / timeline / checklist / SOAP), the
caller now supplies four structured inputs collected from the user at
request time, and this module assembles the right prompt from reusable
fragments.

Drop this file into app/ai/ in either repo (or a shared package both
import) and replace the hardcoded *_SYSTEM_PROMPT constants with calls to
build_system_prompt(...) / build_user_prompt(...).

-----------------------------------------------------------------------
INPUTS (all pre-defined choices — surface these as dropdowns/checkboxes
in the UI, do not accept free text)
-----------------------------------------------------------------------
1. context_type   : where/what kind of encounter this is
2. attendees      : who was in the room (multi-select)
3. purpose        : what output the user wants
4. detail_level   : how much transcript detail should survive into output
"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------
# 1. Predefined option sets
# ---------------------------------------------------------------------

ContextType = Literal[
    "appointment",  # outpatient clinic visit
    "ward_round",  # inpatient rounding
    "operating_room",  # surgical case
    "procedure",  # non-OR procedure (e.g. bedside, endoscopy)
    "telehealth",  # remote consult
    "other",
]

AttendeeRole = Literal[
    "doctor",
    "nurse",
    "patient",
    "patient_companion",
    "surgeon",
    "anesthetist",
    "scrub_tech",
    "resident",
    "interpreter",
    "other_staff",
]

Purpose = Literal[
    "summary",  # short plain-language recap
    "soap_note",  # structured SOAP clinical note
    "clinical_document",  # formal document (op note / consult letter style)
    "timeline",  # timestamped event log
    "checklist_verification",  # e.g. WHO Surgical Safety Checklist
    "full_transcript_review",  # cleaned, role-tagged transcript / role map
    "transcript_only",  # transcript + speaker roles, no clinical output (caller writes the note)
]

DetailLevel = Literal[
    "verbatim",  # keep everything, including filler/hesitation, minimal cleanup
    "standard",  # cleaned up, condensed, natural sentences, no filler
    "key_points",  # bullet-level highlights only, no narrative prose
]


# ---------------------------------------------------------------------
# 2. Fragment libraries — each keyed by the option that selects it
# ---------------------------------------------------------------------

CONTEXT_FRAGMENTS: dict[str, str] = {
    "appointment": (
        "This is an outpatient clinic appointment: a scheduled, relatively short "
        "conversation between a clinician and a patient, typically focused on a "
        "specific complaint, follow-up, or check-in."
    ),
    "ward_round": (
        "This is an inpatient ward round: a clinician (often with a team) visits "
        "an admitted patient's bedside to review status, update the plan, and "
        "answer questions. Expect brief, status-oriented exchanges."
    ),
    "operating_room": (
        "This is an intraoperative recording from the operating room during a "
        "surgical case. Expect terse, procedural, task-focused speech: calls for "
        "instruments, vitals reports, counts, and checklist confirmations."
    ),
    "procedure": (
        "This is a non-OR clinical procedure (e.g. bedside procedure, endoscopy, "
        "minor intervention). Expect procedural narration interspersed with "
        "patient reassurance and monitoring."
    ),
    "telehealth": (
        "This is a remote/telehealth consultation conducted over audio or video. "
        "Expect occasional technical asides (connection issues, audio quality) "
        "that should NOT be treated as clinical content."
    ),
    "other": (
        "This is a clinical conversation whose exact setting was not further "
        "specified. Infer structure cautiously from context."
    ),
}

# Only the cues for attendees actually selected are included, keeping the
# role-identification portion of the prompt short and relevant.
ATTENDEE_ROLE_CUES: dict[str, str] = {
    "doctor": (
        "Doctor: asks diagnostic/clinical questions, gives instructions, states "
        "diagnoses or plans, uses clinical terminology."
    ),
    "nurse": (
        "Nurse: coordinates care tasks, confirms counts/checklist items, relays "
        "information between doctor and patient, handles logistics."
    ),
    "patient": (
        "Patient: reports symptoms, answers questions about their own health, "
        "describes personal experience, asks questions in lay language."
    ),
    "patient_companion": (
        "Patient companion (family/friend): may speak on the patient's behalf, "
        "ask clarifying questions, or provide collateral history, but is not "
        "the subject of care."
    ),
    "surgeon": (
        "Surgeon: narrates procedural steps, calls for instruments, directs the "
        "surgical team, announces incisions/closures."
    ),
    "anesthetist": (
        "Anesthetist/anesthesiologist: reports vitals, administers and discusses "
        "drugs, manages the anesthesia plan, monitors patient status."
    ),
    "scrub_tech": (
        "Scrub tech: manages instruments and sponge/instrument counts, hands "
        "items to the surgeon, confirms counts."
    ),
    "resident": (
        "Resident/trainee: may assist, ask questions, or perform parts of the "
        "encounter under supervision; role can overlap with doctor/surgeon."
    ),
    "interpreter": (
        "Interpreter: relays speech between languages; their own words should "
        "generally NOT be attributed as independent clinical content."
    ),
    "other_staff": (
        "Other staff: supporting personnel (e.g. tech, aide) not covered by the "
        "roles above."
    ),
}

# Purpose-specific task instructions + output schema.
# JSON shapes match the Pydantic models each service validates against.
PURPOSE_FRAGMENTS: dict[str, str] = {
    "summary": (
        "TASK: Produce a short, plain-language summary of what happened in this "
        "encounter, suitable for a patient or a colleague catching up quickly.\n"
        "Return JSON only:\n"
        "{\n"
        '  "summary": "...",\n'
        '  "key_points": ["...", "..."],\n'
        '  "follow_up": "...",\n'
        '  "flags": ["..."]\n'
        "}"
    ),
    "soap_note": (
        "TASK: Produce a structured SOAP note and, in the same pass, the chart fields, vitals and "
        "measurements a display system copies without rewriting.\n"
        "Rules: use ONLY information explicitly present in the transcript; do not "
        'infer or fabricate; if a SOAP section has no content, write "Not discussed"; '
        "flag any discrepancies (e.g. a reported symptom the clinician did not "
        "acknowledge).\n"
        "Chart rules: each chart field holds only what belongs to it; use an empty string when "
        "nothing was said for it (never \"Not discussed\"). ChiefComplaint is one short line in the "
        "patient's words. HPI covers onset, duration, character, severity and modifiers. "
        "A question that lists several symptoms is answered only for the ones the reply names: "
        "for \"Any nausea, vision changes, or neck stiffness?\" answered \"No nausea\", write only "
        "\"No nausea\"; vision changes and neck stiffness are left out, never written as negative. "
        "MedicalHistory holds chronic conditions and regular medicines stated in the visit, each "
        "medicine with its dose and timing as spoken, even when the drug name looks misheard "
        "(keep the heard wording, e.g. \"less than a pearl 10 milligrams each morning\", and add a flag). "
        "Keep the speaker's own words, never a clinical rewording: \"light bothers me a little\" stays "
        "\"light bothers the patient a little\" (not \"light sensitivity\" or \"photophobia\"); "
        "\"weakness on one side\" stays as said (not \"unilateral weakness\"). "
        "Keep who reported each fact: a relative's report is written as theirs "
        "(\"daughter reports poor eating since yesterday\"), never as the patient's. "
        "Include the character of pain when stated (\"dull ache\"). "
        "PhysicalExamination holds only findings the clinician stated. TreatmentPlans includes "
        "medications, advice, follow-up and return precautions (safety-net advice). "
        "Vitals and measurements are numbers as spoken (strings, no units); omit a key that was not said.\n"
        "Speaker labels come from automatic diarization and may be wrong; decide who said a line "
        "from its content (e.g. \"I will record your vitals\" is the clinician).\n"
        "Return JSON only:\n"
        "{\n"
        '  "subjective": "...",\n'
        '  "objective": "...",\n'
        '  "assessment": "...",\n'
        '  "plan": "...",\n'
        '  "medications_mentioned": ["..."],\n'
        '  "follow_up": "...",\n'
        '  "flags": ["..."],\n'
        '  "chart": {"ChiefComplaint": "", "HPI": "", "MedicalHistory": "", "SurgicalHistory": "", '
        '"FamilyAndSocialHistory": "", "OtherSubjective": "", "Vitals": "", "PhysicalExamination": "", '
        '"Assessments": "", "DiagnosticImagesAndTests": "", "Procedures": "", "TreatmentPlans": ""},\n'
        '  "vitals": {"temperature_c": "", "spo2_pct": "", "bp_systolic": "", "bp_diastolic": "", '
        '"pulse_rate": "", "pain_score": "", "resp_rate": ""},\n'
        '  "measurements": {"weight_kg": "", "height_cm": "", "bmi": "", "head_circumference_cm": "", "note": ""}\n'
        "}"
    ),
    "clinical_document": (
        "TASK: Produce a formal clinical document (e.g. consult note / operative "
        "note style) suitable for the medical record.\n"
        "Rules: professional, third-person clinical register; only explicitly "
        "stated facts; no fabricated findings.\n"
        "Return JSON only:\n"
        "{\n"
        '  "title": "...",\n'
        '  "body": "...",\n'
        '  "attendees_listed": ["..."],\n'
        '  "sections": {"heading": "content"},\n'
        '  "flags": ["..."]\n'
        "}"
    ),
    "timeline": (
        "TASK: Extract a timestamped event timeline.\n"
        "Rules: preserve EXACT timestamps from the transcript, do not estimate "
        "or round; do not infer doses/drugs/results not explicitly stated — use "
        '"unclear" when ambiguous.\n'
        "Return JSON only:\n"
        "{\n"
        '  "events": [{"timestamp": "HH:MM:SS", "type": '
        '"incision|medication|count|vitals_report|checklist|other", '
        '"speaker_role": "...", "description": "..."}],\n'
        '  "medications_administered": [{"timestamp": "...", "drug": "...", '
        '"dose": "...", "administered_by_role": "..."}],\n'
        '  "instrument_counts": [{"timestamp": "...", '
        '"type": "sponge_count|instrument_count", '
        '"result": "correct|discrepancy_noted|unclear", "reported_by_role": "..."}]\n'
        "}"
    ),
    "checklist_verification": (
        "TASK: Verify checklist completion (e.g. WHO Surgical Safety Checklist "
        "phases: sign-in, time-out, sign-out — adapt phases to context if this "
        "is not an OR case).\n"
        "Rules: ONLY mark an item confirmed if explicitly verbalized; never "
        "assume completion.\n"
        "Return JSON only:\n"
        "{\n"
        '  "sign_in": {"completed": true, "items_confirmed": ["..."], "items_missing": ["..."]},\n'
        '  "time_out": {"completed": true, "items_confirmed": ["..."], "items_missing": ["..."]},\n'
        '  "sign_out": {"completed": true, "items_confirmed": ["..."], "items_missing": ["..."]}\n'
        "}\n"
        "Standard sign-in items: patient identity, site marked, anesthesia plan, "
        "allergies, consent.\n"
        "Standard time-out items: team introductions, procedure confirmation, "
        "anticipated critical events.\n"
        "Standard sign-out items: procedure recorded, instrument count, specimen "
        "labeling, equipment issues."
    ),
    "full_transcript_review": (
        "TASK: Return a cleaned, role-tagged version of the transcript and "
        "classify each speaker label into a role based on the attendee cues "
        "above. Use an OPEN role set — do not force a listed role if evidence "
        "is weak.\n"
        "Return JSON only:\n"
        "{\n"
        '  "transcript": [{"timestamp": "...", "role": "...", "text": "..."}],\n'
        '  "role_map": {\n'
        '    "SPEAKER_00": {"role": "...", "confidence": "high|medium|low", '
        '"needs_review": false}\n'
        "  },\n"
        '  "reasoning": "1-2 sentences per speaker or overall justification"\n'
        "}\n"
        "For two-party visits, role_map values MAY be plain role strings "
        '("doctor"|"patient"|"other") with top-level confidence instead of '
        "per-speaker objects, if that matches the caller.\n"
        "Mark needs_review=true for any role with confidence below medium when "
        "using per-speaker objects."
    ),
}

MEDICAL_TERMINOLOGY_FRAGMENT = (
    "MEDICAL TERMINOLOGY (mandatory)\n"
    "1. Copy medical terms exactly as spoken: drug names, doses, units, frequencies, routes, diagnoses, "
    "anatomy, test names, abbreviations (HbA1c, CBC, BP, PRN) and every number. Do not paraphrase them, "
    "expand or shorten an abbreviation, convert a unit, round a number, swap a brand and a generic name, "
    "or replace a lay term with a clinical one (\"high blood pressure\" stays \"high blood pressure\"; it is "
    "not rewritten as \"hypertension\" in the patient's history).\n"
    "2. Speech recognition errors: if a phrase is most likely a misheard drug or medical term (for example "
    "\"less than a pearl 10 mg\" for \"lisinopril 10 mg\"), do NOT silently correct it. Keep the transcript "
    "wording, and if the output schema has a flags list add: "
    "\"Possible transcription error: heard '<heard>', likely '<likely>'\". Only the physician confirms a correction.\n"
    "3. Arabic and mixed speech: keep drug names, doses and numbers in the form they were spoken, even when "
    "the output is written in another language. Translate the surrounding words only.\n"
    "4. Negatives and findings: record a negative only when the patient or clinician said it. A question with "
    "no answer (\"Any vision changes?\" and no reply) is not a negative and is left out. Never write "
    "\"denies X\" unless the patient denied X.\n"
    "5. Hedges stay: \"possible\", \"maybe\", \"patient unsure\", \"ربما\" are kept in the text.\n"
    "6. Attribution stays: if a relative or companion reported something, write it as their report "
    "(\"daughter reports poor eating since yesterday\"), not as the patient's own statement."
)

DETAIL_LEVEL_FRAGMENTS: dict[str, str] = {
    "verbatim": (
        "DETAIL LEVEL: Verbatim. Preserve wording as closely as possible, "
        "including hesitations or informal phrasing where they carry meaning. "
        "Do not paraphrase away specific numbers, doses, or quoted statements."
    ),
    "standard": (
        "DETAIL LEVEL: Standard. Clean up filler words and false starts; write "
        "in natural, condensed sentences while preserving every clinically "
        "relevant fact."
    ),
    "key_points": (
        "DETAIL LEVEL: Key points only. Compress to the essential facts as "
        "short bullet-style entries wherever the schema allows free text; omit "
        "conversational framing entirely."
    ),
}


# ---------------------------------------------------------------------
# 3. Request object + prompt builders
# ---------------------------------------------------------------------

class TranscriptionRequest(BaseModel):
    context_type: ContextType
    attendees: List[AttendeeRole] = Field(default_factory=list)
    purpose: Purpose = "summary"
    detail_level: DetailLevel = "standard"


def as_transcription_request(value: TranscriptionRequest | BaseModel | dict | None) -> TranscriptionRequest:
    """Normalize API options, stored JSON, or a request model into TranscriptionRequest."""
    if value is None:
        raise ValueError("transcription request is required")
    if isinstance(value, TranscriptionRequest):
        return value
    if hasattr(value, "to_transcription_request"):
        return value.to_transcription_request()
    if isinstance(value, BaseModel):
        return TranscriptionRequest.model_validate(value.model_dump())
    return TranscriptionRequest.model_validate(value)


def build_system_prompt(req: TranscriptionRequest) -> str:
    """Assemble the system prompt from context + attendee + purpose + detail fragments."""
    parts: list[str] = []

    parts.append(
        "You are a clinical conversation intelligence assistant. Use ONLY "
        "information explicitly present in the transcript provided by the "
        "user. Never fabricate clinical details."
    )

    parts.append(CONTEXT_FRAGMENTS.get(req.context_type, CONTEXT_FRAGMENTS["other"]))

    if req.attendees:
        cues = "\n".join(
            f"- {ATTENDEE_ROLE_CUES[a]}" for a in req.attendees if a in ATTENDEE_ROLE_CUES
        )
        parts.append(
            "ATTENDEES PRESENT — use these behavioral cues to identify who is "
            f"speaking:\n{cues}"
        )

    parts.append(PURPOSE_FRAGMENTS.get(req.purpose, PURPOSE_FRAGMENTS["summary"]))
    parts.append(MEDICAL_TERMINOLOGY_FRAGMENT)
    parts.append(DETAIL_LEVEL_FRAGMENTS.get(req.detail_level, DETAIL_LEVEL_FRAGMENTS["standard"]))

    parts.append("Do not include markdown or commentary outside the JSON object.")

    return "\n\n".join(parts)


def build_user_prompt(req: TranscriptionRequest, transcript_text: str) -> str:
    """Assemble the user-turn prompt carrying the actual transcript."""
    return (
        f"Context: {req.context_type}\n"
        f"Attendees: {', '.join(req.attendees) if req.attendees else 'unspecified'}\n"
        f"Requested output: {req.purpose}\n"
        f"Detail level: {req.detail_level}\n\n"
        "Transcript:\n"
        f"{transcript_text}\n\n"
        "Return the JSON described in the system prompt."
    )
