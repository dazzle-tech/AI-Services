"""
summary_parser.py
-----------------
Validates and converts the raw JSON string returned by GPT-4o into a typed
SBARSummary object.

Keeping this separate means:
- If the output schema changes, only this file needs updating.
- Validation failures are caught here before they can propagate.
- The parser can be tested with static JSON strings — no API call needed.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from app.models.schemas import SBARSummary


def parse_and_validate(
    raw_json: str,
    patient_id: str,
    generated_at: Optional[datetime] = None,
) -> SBARSummary:
    """
    Parses the raw GPT-4o JSON string into a validated SBARSummary.

    Args:
        raw_json:   The string returned by gpt_service.call_gpt().
        patient_id: Used to override the patient_id field and for error messages.
                    GPT receives the ID in the prompt, but we enforce it here too.

    Returns:
        A validated SBARSummary Pydantic model.

    Raises:
        ValueError: If the JSON is malformed or fails schema validation.
    """
    # Step 1: Parse JSON string
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"GPT returned invalid JSON for patient '{patient_id}': {e}\n"
            f"Raw output was: {raw_json[:300]}"
        )

    # Step 2: The model must return a JSON object — an array or scalar is a failure,
    # not something to index into.
    if not isinstance(data, dict):
        raise ValueError(
            f"GPT returned a JSON {type(data).__name__}, not an object, for patient "
            f"'{patient_id}'. Raw output was: {raw_json[:300]}"
        )

    # Step 3: Enforce correct patient_id regardless of what GPT returned
    data["patient_id"] = patient_id

    # Step 4: Stamp generation time (caller may pass a shared batch timestamp)
    data["generated_at"] = generated_at or datetime.now(timezone.utc)

    # Step 5: Validate against schema
    try:
        return SBARSummary.model_validate(data)
    except ValidationError as e:
        raise ValueError(
            f"GPT output failed schema validation for patient '{patient_id}':\n{e}\n"
            f"Parsed data was: {data}"
        )
