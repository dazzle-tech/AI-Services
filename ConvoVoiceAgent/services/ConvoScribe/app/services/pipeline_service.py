"""Shared audio processing pipeline (transcription, roles, summarization)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.ai.role_identification import identify_roles
from app.ai.summarization import summarize_transcript
from app.ai.unified_prompts import TranscriptionRequest
from app.models.schemas import (
    ClinicalDocument,
    NarrativeSummary,
    RawTranscript,
    RoleIdentificationResult,
    SOAPSummary,
    TranscriptSegment,
    TranscriptionRequestOptions,
)
from app.transcription import get_transcription_service
from app.transcription.base import DiarizedSegment


@dataclass
class PipelineResult:
    raw_transcript: RawTranscript
    role_map: Dict[str, str]
    role_confidence: str
    role_reasoning: str
    needs_review: bool
    summary: Optional[SOAPSummary]
    narrative_summary: Optional[NarrativeSummary] = None
    clinical_document: Optional[ClinicalDocument] = None


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


def identify_speaker_roles(
    segments: List[Dict[str, Any]],
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | dict | None = None,
) -> RoleIdentificationResult:
    return identify_roles(segments, prompt_options=resolve_prompt_options(prompt_options))


def generate_clinical_summary(
    segments: List[Dict[str, Any]],
    role_map: Dict[str, str],
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | dict | None = None,
):
    return summarize_transcript(segments, role_map, prompt_options=resolve_prompt_options(prompt_options))


def process_audio(
    audio_bytes: bytes,
    filename: str,
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | dict | None = None,
) -> PipelineResult:
    """Run ASR, diarization, role identification, and purpose-specific clinical output."""
    options = resolve_prompt_options(prompt_options)
    segment_dicts = transcribe_audio(audio_bytes, filename)
    role_result = identify_speaker_roles(segment_dicts, prompt_options=options)

    summary: Optional[SOAPSummary] = None
    narrative_summary: Optional[NarrativeSummary] = None
    clinical_document: Optional[ClinicalDocument] = None
    needs_review = role_result.confidence == "low"
    # NOTE: timeline / checklist_verification exist in unified_prompts but ConvoScribe
    # has no timeline or WHO-checklist modules, so those purposes stop after role ID.
    if not needs_review and options.purpose in {
        "soap_note",
        "summary",
        "clinical_document",
        "full_transcript_review",
    }:
        output = generate_clinical_summary(segment_dicts, role_result.role_map, prompt_options=options)
        if isinstance(output, NarrativeSummary):
            narrative_summary = output
        elif isinstance(output, ClinicalDocument):
            clinical_document = output
        else:
            summary = output

    return PipelineResult(
        raw_transcript=_to_raw_transcript(segment_dicts),
        role_map=role_result.role_map,
        role_confidence=role_result.confidence,
        role_reasoning=role_result.reasoning,
        needs_review=needs_review,
        summary=summary,
        narrative_summary=narrative_summary,
        clinical_document=clinical_document,
    )
