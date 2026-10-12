"""Speaker role identification via OpenAI."""

from typing import Any, Dict, List

from app.ai.client import AIClient
from app.ai.prompts import format_diarized_transcript
from app.ai.unified_prompts import (
    TranscriptionRequest,
    as_transcription_request,
    build_system_prompt,
    build_user_prompt,
)
from app.core import config
from app.models.schemas import RoleIdentificationResult, TranscriptionRequestOptions


def identify_roles(
    segments: List[dict],
    client: AIClient | None = None,
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | None = None,
) -> RoleIdentificationResult:
    transcript_text = format_diarized_transcript(segments)
    req = _role_request(prompt_options)

    if config.settings.use_llm_stub:
        payload = _stub_identify_roles(segments)
    else:
        llm = client or AIClient()
        payload = llm.complete_json(
            model=config.settings.role_id_model,
            system_prompt=build_system_prompt(req),
            user_prompt=build_user_prompt(req, transcript_text),
        )

    return RoleIdentificationResult.model_validate(_normalize_role_payload(payload))


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
    """Accept nested OR-style role objects or ConvoScribe plain role strings."""
    role_map = payload.get("role_map", {})
    normalized: Dict[str, str] = {}
    confidences: List[str] = []
    for speaker, value in role_map.items():
        if isinstance(value, dict):
            normalized[speaker] = str(value.get("role", "other"))
            if value.get("confidence"):
                confidences.append(str(value["confidence"]))
        else:
            normalized[speaker] = str(value)
    # NOTE: ConvoScribe still validates doctor|patient|other; attendee roles such as
    # patient_companion are mapped to "other" here rather than expanding SpeakerRole.
    mapped = {}
    for speaker, role in normalized.items():
        if role in {"doctor", "patient", "other"}:
            mapped[speaker] = role
        elif role == "patient_companion":
            mapped[speaker] = "other"
        elif role in {"surgeon", "anesthetist", "nurse", "resident"}:
            mapped[speaker] = "doctor"
        else:
            mapped[speaker] = "other"
    confidence = payload.get("confidence") or _lowest_confidence(confidences) or "medium"
    return {
        "role_map": mapped,
        "confidence": confidence,
        "reasoning": payload.get("reasoning", ""),
    }


def _lowest_confidence(confidences: List[str]) -> str | None:
    order = {"low": 1, "medium": 2, "high": 3}
    if not confidences:
        return None
    return min(confidences, key=lambda item: order.get(item, 2))


def _stub_identify_roles(segments: List[dict]) -> Dict[str, Any]:
    """Rule-based placeholder for pipeline testing."""
    speakers = sorted({segment["speaker_label"] for segment in segments})
    texts = " ".join(segment["text"].lower() for segment in segments)

    if len(speakers) >= 3:
        role_map: Dict[str, str] = {}
        for speaker in speakers:
            speaker_text = " ".join(
                segment["text"] for segment in segments if segment["speaker_label"] == speaker
            ).lower()
            if any(
                cue in speaker_text
                for cue in ("blood pressure", "medications", "how can i help", "examine", "i'll check")
            ):
                role_map[speaker] = "doctor"
            elif any(cue in speaker_text for cue in ("my mother", "my father", "my husband", "my wife")):
                role_map[speaker] = "other"
            elif any(cue in speaker_text for cue in ("i feel", "i've been", "i have been", "my throat")):
                role_map[speaker] = "patient"
            else:
                role_map[speaker] = "other"
        return {
            "role_map": role_map,
            "confidence": "high",
            "reasoning": "Three speakers detected; clinical, caregiver, and patient speech patterns separated.",
        }

    doctor_signals = ("examine", "diagnosis", "prescribe", "follow up if", "what brings you")
    patient_signals = ("i've had", "my throat", "it hurts", "symptoms")

    first_text = next((s["text"].lower() for s in segments if s["speaker_label"] == speakers[0]), "")
    second_text = next(
        (s["text"].lower() for s in segments if len(speakers) > 1 and s["speaker_label"] == speakers[1]),
        "",
    )

    doctor_first = any(token in first_text for token in doctor_signals)
    patient_second = any(token in second_text for token in patient_signals)

    if len(speakers) == 2 and doctor_first and patient_second:
        return {
            "role_map": {speakers[0]: "doctor", speakers[1]: "patient"},
            "confidence": "high",
            "reasoning": "Speaker 0 asks clinical questions; speaker 1 reports symptoms.",
        }

    if "good morning" in texts and "sore throat" in texts:
        return {
            "role_map": {speakers[0]: "doctor", speakers[1]: "patient"},
            "confidence": "high" if len(speakers) == 2 else "medium",
            "reasoning": "Standard two-speaker visit pattern detected.",
        }

    role_map = {speakers[0]: "doctor"}
    if len(speakers) > 1:
        role_map[speakers[1]] = "patient"
    return {
        "role_map": role_map,
        "confidence": "low",
        "reasoning": "Insufficient conversational cues to confidently assign roles.",
    }
