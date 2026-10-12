"""Intraoperative timeline extraction via OpenAI."""

import re
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
from app.models.schemas import TimelineExtractionResult, TranscriptionRequestOptions


def extract_timeline(
    segments: List[dict],
    role_map: dict,
    client: AIClient | None = None,
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | None = None,
) -> TimelineExtractionResult:
    transcript_text = format_diarized_transcript(segments, role_map)
    req = _timeline_request(prompt_options)

    if settings.use_llm_stub:
        payload = _stub_extract_timeline(segments, role_map)
    else:
        llm = client or AIClient()
        payload = llm.complete_json(
            model=settings.record_model,
            system_prompt=build_system_prompt(req),
            user_prompt=build_user_prompt(req, transcript_text),
        )

    return TimelineExtractionResult.model_validate(payload)


def _timeline_request(
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | dict | None,
) -> TranscriptionRequest:
    if prompt_options is None:
        base = TranscriptionRequestOptions().to_transcription_request()
    else:
        base = as_transcription_request(prompt_options)
    return base.model_copy(update={"purpose": "timeline"})


def _format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _get_role(role_map: dict, speaker: str) -> str:
    entry = role_map.get(speaker, {})
    if isinstance(entry, dict):
        return entry.get("role", "unidentified")
    return str(entry)


def _stub_extract_timeline(segments: List[dict], role_map: dict) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    medications: List[Dict[str, Any]] = []
    counts: List[Dict[str, Any]] = []

    for segment in segments:
        text = segment["text"]
        text_lower = text.lower()
        ts = _format_timestamp(segment["start_time"])
        role = _get_role(role_map, segment["speaker_label"])

        if "incision" in text_lower:
            events.append(
                {"timestamp": ts, "type": "incision", "speaker_role": role, "description": text}
            )
        if "sign in" in text_lower or "time out" in text_lower or "sign out" in text_lower:
            events.append(
                {"timestamp": ts, "type": "checklist", "speaker_role": role, "description": text}
            )
        if "blood pressure" in text_lower or "heart rate" in text_lower:
            events.append(
                {"timestamp": ts, "type": "vitals_report", "speaker_role": role, "description": text}
            )

        med_match = re.search(
            r"giving\s+(\w+)\s+(\d+\s*(?:milligrams|mg|mcg|units)?)",
            text_lower,
        )
        if med_match:
            medications.append(
                {
                    "timestamp": ts,
                    "drug": med_match.group(1),
                    "dose": med_match.group(2).strip(),
                    "administered_by_role": role,
                }
            )

        if "count correct" in text_lower:
            count_type = "sponge_count" if "sponge" in text_lower else "instrument_count"
            counts.append(
                {
                    "timestamp": ts,
                    "type": count_type,
                    "result": "correct",
                    "reported_by_role": role,
                }
            )

    return {
        "events": events,
        "medications_administered": medications,
        "instrument_counts": counts,
    }
