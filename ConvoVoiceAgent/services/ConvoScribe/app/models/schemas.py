"""Pydantic request/response schemas."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.ai.unified_prompts import (
    AttendeeRole,
    ContextType,
    DetailLevel,
    Purpose,
    TranscriptionRequest,
)


SpeakerRole = Literal["doctor", "patient", "other"]
ConfidenceLevel = Literal["high", "medium", "low"]


class TranscriptSegment(BaseModel):
    speaker_label: str
    start_time: float
    end_time: float
    text: str


class RawTranscript(BaseModel):
    segments: List[TranscriptSegment]


class RoleIdentificationResult(BaseModel):
    role_map: Dict[str, SpeakerRole]
    confidence: ConfidenceLevel
    reasoning: str


class SOAPSummary(BaseModel):
    subjective: str
    objective: str
    assessment: str
    plan: str
    medications_mentioned: List[str] = Field(default_factory=list)
    follow_up: str
    flags: List[str] = Field(default_factory=list)


class NarrativeSummary(BaseModel):
    summary: str
    key_points: List[str] = Field(default_factory=list)
    follow_up: str = "Not discussed"
    flags: List[str] = Field(default_factory=list)


class ClinicalDocument(BaseModel):
    title: str
    body: str
    attendees_listed: List[str] = Field(default_factory=list)
    sections: Dict[str, str] = Field(default_factory=dict)
    flags: List[str] = Field(default_factory=list)


class TranscriptionRequestOptions(BaseModel):
    context_type: ContextType = "appointment"
    attendees: List[AttendeeRole] = Field(default_factory=lambda: ["doctor", "patient"])
    purpose: Purpose = "soap_note"
    detail_level: DetailLevel = "standard"

    def to_transcription_request(self) -> TranscriptionRequest:
        return TranscriptionRequest(
            context_type=self.context_type,
            attendees=self.attendees,
            purpose=self.purpose,
            detail_level=self.detail_level,
        )


class SessionCreateRequest(BaseModel):
    patient_id: str
    prompt_options: Optional[TranscriptionRequestOptions] = None


class SessionCreateResponse(BaseModel):
    session_id: UUID
    status: str


class SessionResponse(BaseModel):
    id: UUID
    status: str
    created_at: datetime
    patient_id: str
    clinician_id: str
    needs_review: bool
    clinician_approved: bool
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    raw_transcript: Optional[RawTranscript] = None
    role_map: Optional[Dict[str, SpeakerRole]] = None
    role_confidence: Optional[str] = None
    role_reasoning: Optional[str] = None
    summary: Optional[SOAPSummary] = None
    narrative_summary: Optional[NarrativeSummary] = None
    clinical_document: Optional[ClinicalDocument] = None
    error_message: Optional[str] = None


class TranscriptResponse(BaseModel):
    session_id: UUID
    raw_transcript: RawTranscript


class RoleUpdateRequest(BaseModel):
    role_map: Dict[str, SpeakerRole]


class ApproveRequest(BaseModel):
    clinician_id: str


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
    details: Dict[str, Any] = Field(default_factory=dict)


class AnalyzeJsonRequest(BaseModel):
    """Raw JSON body for POST /api/v1/analyze (Content-Type: application/json)."""

    audio_base64: str = Field(..., description="Base64-encoded .wav, .mp3, or .m4a audio")
    filename: str = "audio.wav"
    context_type: ContextType = "appointment"
    attendees: List[AttendeeRole] = Field(
        default_factory=lambda: ["doctor", "nurse", "patient", "patient_companion"]
    )
    purpose: Purpose = "soap_note"
    detail_level: DetailLevel = "standard"


class AnalyzeAudioResponse(BaseModel):
    raw_transcript: RawTranscript
    role_map: Dict[str, SpeakerRole]
    role_confidence: ConfidenceLevel
    role_reasoning: str
    needs_review: bool
    summary: Optional[SOAPSummary] = None
    narrative_summary: Optional[NarrativeSummary] = None
    clinical_document: Optional[ClinicalDocument] = None


def options_from_form(
    context_type: str | None,
    attendees: str | None,
    purpose: str | None,
    detail_level: str | None,
) -> TranscriptionRequestOptions:
    """Build prompt options from optional multipart form fields."""
    import json

    kwargs: Dict[str, Any] = {}
    if context_type:
        kwargs["context_type"] = context_type
    if attendees:
        raw = attendees.strip()
        if raw.startswith("["):
            kwargs["attendees"] = json.loads(raw)
        else:
            kwargs["attendees"] = [part.strip() for part in raw.split(",") if part.strip()]
    if purpose:
        kwargs["purpose"] = purpose
    if detail_level:
        kwargs["detail_level"] = detail_level
    return TranscriptionRequestOptions.model_validate(kwargs)
