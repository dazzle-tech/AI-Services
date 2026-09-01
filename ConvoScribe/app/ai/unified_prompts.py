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
        "TASK: Produce a structured SOAP note.\n"
        "Rules: use ONLY information explicitly present in the transcript; do not "
        'infer or fabricate; if a section has no content, write "Not discussed"; '
        "flag any discrepancies (e.g. a reported symptom the clinician did not "
        "acknowledge).\n"
        "Return JSON only:\n"
        "{\n"
        '  "subjective": "...",\n'
        '  "objective": "...",\n'
        '  "assessment": "...",\n'
        '  "plan": "...",\n'
        '  "medications_mentioned": ["..."],\n'
        '  "follow_up": "...",\n'
        '  "flags": ["..."]\n'
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
