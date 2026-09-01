"""Surgical team role identification via OpenAI."""

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
from app.models.schemas import RoleIdentificationResult, TranscriptionRequestOptions

CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1}


def identify_roles(
    segments: List[dict],
    scheduled_team: dict | None = None,
    client: AIClient | None = None,
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | None = None,
) -> RoleIdentificationResult:
    transcript_text = format_diarized_transcript(segments)
    req = _role_request(prompt_options)

    if settings.use_llm_stub:
        payload = _stub_identify_roles(segments)
    else:
        llm = client or AIClient()
        user_prompt = build_user_prompt(req, transcript_text)
        if scheduled_team:
            user_prompt += f"\nScheduled team (if known): {scheduled_team}\n"
        payload = llm.complete_json(
            model=settings.role_id_model,
            system_prompt=build_system_prompt(req),
            user_prompt=user_prompt,
        )

    result = RoleIdentificationResult.model_validate(_normalize_role_payload(payload))
    _apply_review_flags(result)
    return result


def _role_request(
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | dict | None,
) -> TranscriptionRequest:
    if prompt_options is None:
        base = TranscriptionRequestOptions().to_transcription_request()
    else:
        base = as_transcription_request(prompt_options)
    # Role ID always needs the role_map schema, not the caller's output purpose.
    return base.model_copy(update={"purpose": "full_transcript_review"})


def _normalize_role_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    role_map = payload.get("role_map", {})
    normalized: Dict[str, Any] = {}
    for speaker, value in role_map.items():
        if isinstance(value, dict):
            normalized[speaker] = value
        else:
            normalized[speaker] = {"role": str(value), "confidence": "medium", "needs_review": False}
    return {"role_map": normalized, "reasoning": payload.get("reasoning", "")}


def _apply_review_flags(result: RoleIdentificationResult) -> None:
    threshold = settings.role_confidence_threshold
    threshold_level = CONFIDENCE_ORDER.get(threshold, 2)
    for assignment in result.role_map.values():
        level = CONFIDENCE_ORDER.get(assignment.confidence, 1)
        if level < threshold_level:
            assignment.needs_review = True


def _stub_identify_roles(segments: List[dict]) -> Dict[str, Any]:
    speakers = sorted({segment["speaker_label"] for segment in segments})
    role_map: Dict[str, Dict[str, Any]] = {}

    for speaker in speakers:
        speaker_text = " ".join(
            segment["text"] for segment in segments if segment["speaker_label"] == speaker
        ).lower()

        if any(cue in speaker_text for cue in ("incision", "scalpel", "suture", "closing", "specimen")):
            role_map[speaker] = {"role": "surgeon", "confidence": "high", "needs_review": False}
        elif any(
            cue in speaker_text
            for cue in ("blood pressure", "heart rate", "propofol", "anesthesia", "vitals")
        ):
            role_map[speaker] = {"role": "anesthetist", "confidence": "high", "needs_review": False}
        elif any(cue in speaker_text for cue in ("count correct", "sponge count", "instrument count", "time out", "sign in", "sign out")):
            role_map[speaker] = {"role": "nurse", "confidence": "high", "needs_review": False}
        elif any(cue in speaker_text for cue in ("retractor", "holding", "please")):
            role_map[speaker] = {"role": "unidentified", "confidence": "low", "needs_review": True}
        else:
            role_map[speaker] = {"role": "unidentified", "confidence": "low", "needs_review": True}

    reasoning_parts = []
    for speaker, assignment in role_map.items():
        reasoning_parts.append(f"{speaker}: {assignment['role']} ({assignment['confidence']})")
    return {
        "role_map": role_map,
        "reasoning": "; ".join(reasoning_parts) + ".",
    }
