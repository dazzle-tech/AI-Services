"""Synchronous audio processing pipeline (transcription, roles, timeline, checklist)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.ai.checklist_verification import verify_checklist
from app.ai.role_identification import identify_roles
from app.ai.timeline_extraction import extract_timeline
from app.ai.unified_prompts import TranscriptionRequest
from app.models.schemas import (
    ChecklistVerificationResult,
    RawTranscript,
    RoleIdentificationResult,
    SpeakerRoleAssignment,
    TimelineExtractionResult,
    TranscriptSegment,
    TranscriptionRequestOptions,
)
from app.transcription import get_transcription_service
from app.transcription.base import DiarizedSegment


@dataclass
class PipelineResult:
    raw_transcript: RawTranscript
    role_map: Dict[str, SpeakerRoleAssignment]
    role_reasoning: str
    needs_review: bool
    timeline: Optional[TimelineExtractionResult]
    checklist: Optional[ChecklistVerificationResult]


def _segments_to_dicts(segments: List[DiarizedSegment]) -> List[Dict[str, Any]]:
    return [
        {
            "speaker_label": segment.speaker_label,
            "start_time": segment.start_time,
            "end_time": segment.end_time,
            "text": segment.text,
        }
        for segment in segments
    ]


def _to_raw_transcript(segments: List[Dict[str, Any]]) -> RawTranscript:
    return RawTranscript(
        segments=[
            TranscriptSegment(
                speaker_label=segment["speaker_label"],
                start_time=segment["start_time"],
                end_time=segment["end_time"],
                text=segment["text"],
            )
            for segment in segments
        ]
    )


def resolve_prompt_options(
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | dict | None,
) -> TranscriptionRequestOptions:
    if prompt_options is None:
        return TranscriptionRequestOptions()
    if isinstance(prompt_options, TranscriptionRequestOptions):
        return prompt_options
    if isinstance(prompt_options, TranscriptionRequest):
        return TranscriptionRequestOptions(
            context_type=prompt_options.context_type,
            attendees=prompt_options.attendees,
            purpose=prompt_options.purpose,
            detail_level=prompt_options.detail_level,
        )
    return TranscriptionRequestOptions.model_validate(prompt_options)


def transcribe_audio(audio_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
    transcription = get_transcription_service()
    segments = transcription.transcribe_and_diarize(audio_bytes, filename)
    return _segments_to_dicts(segments)


def process_audio(
    audio_bytes: bytes,
    filename: str,
    scheduled_team: dict | None = None,
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | dict | None = None,
) -> PipelineResult:
    """Run ASR, diarization, role identification, timeline, and checklist verification."""
    options = resolve_prompt_options(prompt_options)
    segment_dicts = transcribe_audio(audio_bytes, filename)
    role_result: RoleIdentificationResult = identify_roles(
        segment_dicts, scheduled_team, prompt_options=options
    )
    needs_review = any(assignment.needs_review for assignment in role_result.role_map.values())

    timeline: Optional[TimelineExtractionResult] = None
    checklist: Optional[ChecklistVerificationResult] = None
    if not needs_review:
        role_dump = {key: value.model_dump() for key, value in role_result.role_map.items()}
        # NOTE: soap_note / summary / clinical_document are in unified_prompts but ORScribe
        # has no summarization module, so those purposes only run role identification.
        if options.purpose in {"timeline", "full_transcript_review"}:
            timeline = extract_timeline(segment_dicts, role_dump, prompt_options=options)
        if options.purpose in {"checklist_verification", "full_transcript_review"}:
            checklist = verify_checklist(segment_dicts, role_dump, prompt_options=options)

    return PipelineResult(
        raw_transcript=_to_raw_transcript(segment_dicts),
        role_map=role_result.role_map,
        role_reasoning=role_result.reasoning,
        needs_review=needs_review,
        timeline=timeline,
        checklist=checklist,
    )
