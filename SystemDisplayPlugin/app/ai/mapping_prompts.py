"""
mapping_prompts.py

System/user prompt builders for non-direct field transforms.
Same fragment-assembly pattern as ORScribe/ConvoScribe unified_prompts.py:
context + purpose frame the task; the model only reshapes existing JSON.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from app.models.schemas import DecoderField

CONTEXT_FRAGMENTS: dict[str, str] = {
    "appointment": "The source JSON is from an outpatient clinic appointment.",
    "ward_round": "The source JSON is from an inpatient ward round.",
    "operating_room": "The source JSON is from an operating-room / intraoperative recording.",
    "procedure": "The source JSON is from a non-OR clinical procedure.",
    "telehealth": "The source JSON is from a remote/telehealth consultation.",
    "other": "The source JSON is from a clinical encounter whose setting was not further specified.",
}

PURPOSE_FRAGMENTS: dict[str, str] = {
    "summary": "The source payload is a short encounter summary (summary / key_points / follow_up).",
    "soap_note": "The source payload is a structured SOAP note (subjective / objective / assessment / plan).",
    "clinical_document": "The source payload is a formal clinical document (title / body / sections).",
    "timeline": "The source payload is a timestamped event timeline (events / medications / counts).",
    "checklist_verification": "The source payload is checklist verification (sign_in / time_out / sign_out).",
    "full_transcript_review": "The source payload is a role-tagged transcript / role map.",
}

TRANSFORM_FRAGMENTS: dict[str, str] = {
    "summarize": "Condensed restatement of the source slice only; do not add facts.",
    "concat": "Join the source slice into one value (use transform_hint as separator if given).",
    "split": "Split the source slice into a list (use transform_hint as separator if given).",
    "extract": "Pull the requested subset out of the source slice; do not rephrase clinical meaning.",
}


def build_system_prompt(*, context: str, purpose: str) -> str:
    parts: list[str] = [
        "You are a field-level mapper for clinical structured data. "
        "Reshape or condense ONLY values already present in the provided source slices. "
        "Never regenerate, infer, or fabricate clinical content.",
        CONTEXT_FRAGMENTS.get(context, CONTEXT_FRAGMENTS["other"]),
        PURPOSE_FRAGMENTS.get(purpose, PURPOSE_FRAGMENTS["summary"]),
        "Return a single JSON object whose keys are exactly the listed field_name values. "
        "Each value must match the field's field_type (string, list, boolean, object, or date as ISO-like string). "
        "Do not include markdown or commentary outside the JSON object.",
    ]
    return "\n\n".join(parts)


def build_user_prompt(
    *,
    context: str,
    purpose: str,
    fields: Sequence[tuple[DecoderField, Any]],
) -> str:
    field_blocks: list[str] = []
    for field, source_slice in fields:
        hint = field.transform_hint or "(none)"
        transform_help = TRANSFORM_FRAGMENTS.get(field.transform, field.transform)
        field_blocks.append(
            "\n".join(
                [
                    f"field_name: {field.field_name}",
                    f"field_type: {field.field_type}",
                    f"transform: {field.transform}",
                    f"transform_hint: {hint}",
                    f"transform_instruction: {transform_help}",
                    f"source_slice: {json.dumps(source_slice, default=str)}",
                ]
            )
        )
    joined = "\n\n---\n\n".join(field_blocks)
    return (
        f"Context: {context}\n"
        f"Purpose (source shape): {purpose}\n\n"
        "Map each field below. Return JSON only, keys = field_name.\n\n"
        f"{joined}"
    )
