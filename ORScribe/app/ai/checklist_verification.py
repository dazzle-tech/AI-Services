"""WHO Surgical Safety Checklist verification via OpenAI."""

from typing import Any, Dict, List

from app.ai.client import AIClient
from app.ai.prompts import format_diarized_transcript
from app.ai.unified_prompts import (
    TranscriptionRequest,
    as_transcription_request,
    build_system_prompt,
    build_user_prompt,
)
from app.core.config import settings
from app.models.schemas import ChecklistVerificationResult, TranscriptionRequestOptions

# NOTE: unified_prompts checklist_verification is WHO sign-in / time-out / sign-out.
# If that shared fragment is ever generalized away from OR phases, restore the
# OR-specific item lists in the prompt here rather than editing unified_prompts.py.
SIGN_IN_ITEMS = [
    "patient identity confirmed",
    "site marked",
    "anesthesia plan reviewed",
    "allergies noted",
    "consent verified",
]
TIME_OUT_ITEMS = [
    "team introductions",
    "procedure confirmation",
    "anticipated critical events reviewed",
]
SIGN_OUT_ITEMS = [
    "procedure recorded",
    "instrument count",
    "specimen labeled",
]


def verify_checklist(
    segments: List[dict],
    role_map: dict,
    client: AIClient | None = None,
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | None = None,
) -> ChecklistVerificationResult:
    transcript_text = format_diarized_transcript(segments, role_map)
    req = _checklist_request(prompt_options)

    if settings.use_llm_stub:
        payload = _stub_verify_checklist(segments)
    else:
        llm = client or AIClient()
        payload = llm.complete_json(
            model=settings.record_model,
            system_prompt=build_system_prompt(req),
            user_prompt=build_user_prompt(req, transcript_text),
        )

    return ChecklistVerificationResult.model_validate(payload)


def _checklist_request(
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | dict | None,
) -> TranscriptionRequest:
    if prompt_options is None:
        base = TranscriptionRequestOptions().to_transcription_request()
    else:
        base = as_transcription_request(prompt_options)
    return base.model_copy(update={"purpose": "checklist_verification"})


def _stub_verify_checklist(segments: List[dict]) -> Dict[str, Any]:
    full_text = " ".join(segment["text"].lower() for segment in segments)

    sign_in_confirmed = []
    sign_in_missing = []
    for item in SIGN_IN_ITEMS:
        keywords = item.split()
        if all(kw in full_text for kw in keywords[:2]):
            sign_in_confirmed.append(item)
        else:
            sign_in_missing.append(item)

    time_out_confirmed = []
    time_out_missing = []
    if "time out" in full_text:
        for item in TIME_OUT_ITEMS:
            keywords = item.split()
            if any(kw in full_text for kw in keywords):
                time_out_confirmed.append(item)
            else:
                time_out_missing.append(item)
    else:
        time_out_missing = list(TIME_OUT_ITEMS)

    sign_out_confirmed = []
    sign_out_missing = []
    if "sign out" in full_text:
        for item in SIGN_OUT_ITEMS:
            keywords = item.split()
            if any(kw in full_text for kw in keywords):
                sign_out_confirmed.append(item)
            else:
                sign_out_missing.append(item)
    else:
        sign_out_missing = list(SIGN_OUT_ITEMS)

    return {
        "sign_in": {
            "completed": len(sign_in_missing) == 0,
            "items_confirmed": sign_in_confirmed,
            "items_missing": sign_in_missing,
        },
        "time_out": {
            "completed": len(time_out_missing) == 0,
            "items_confirmed": time_out_confirmed,
            "items_missing": time_out_missing,
        },
        "sign_out": {
            "completed": len(sign_out_missing) == 0,
            "items_confirmed": sign_out_confirmed,
            "items_missing": sign_out_missing,
        },
    }
