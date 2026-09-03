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


ConfidenceLevel = Literal["high", "medium", "low"]
EventType = Literal[
    "incision",
    "medication",
    "count",
    "vitals_report",
    "checklist",
    "other",
]
CountType = Literal["sponge_count", "instrument_count"]
CountResult = Literal["correct", "discrepancy_noted", "unclear"]


class TranscriptSegment(BaseModel):
    speaker_label: str
    start_time: float
    end_time: float
    text: str


class RawTranscript(BaseModel):
    segments: List[TranscriptSegment]


class SpeakerRoleAssignment(BaseModel):
    role: str
    confidence: ConfidenceLevel
    needs_review: bool = False


class RoleIdentificationResult(BaseModel):
    role_map: Dict[str, SpeakerRoleAssignment]
    reasoning: str


class TimelineEvent(BaseModel):
    timestamp: str
    type: EventType
    speaker_role: str
    description: str


class MedicationEntry(BaseModel):
    timestamp: str
    drug: str
    dose: str
    administered_by_role: str


class InstrumentCountEntry(BaseModel):
    timestamp: str
    type: CountType
    result: CountResult
    reported_by_role: str


class TimelineExtractionResult(BaseModel):
    events: List[TimelineEvent] = Field(default_factory=list)
    medications_administered: List[MedicationEntry] = Field(default_factory=list)
    instrument_counts: List[InstrumentCountEntry] = Field(default_factory=list)


class ChecklistPhaseResult(BaseModel):
    completed: bool
    items_confirmed: List[str] = Field(default_factory=list)
    items_missing: List[str] = Field(default_factory=list)


class ChecklistVerificationResult(BaseModel):
    sign_in: ChecklistPhaseResult
    time_out: ChecklistPhaseResult
    sign_out: ChecklistPhaseResult


class TranscriptionRequestOptions(BaseModel):
    context_type: ContextType = "operating_room"
    attendees: List[AttendeeRole] = Field(
        default_factory=lambda: ["surgeon", "anesthetist", "nurse", "scrub_tech", "resident"]
    )
    purpose: Purpose = "full_transcript_review"
    detail_level: DetailLevel = "standard"

    def to_transcription_request(self) -> TranscriptionRequest:
        return TranscriptionRequest(
            context_type=self.context_type,
            attendees=self.attendees,
            purpose=self.purpose,
            detail_level=self.detail_level,
        )


class CaseCreateRequest(BaseModel):
    procedure_type: str
    scheduled_team: Optional[Dict[str, str]] = None
    ingest_mode: Literal["post_hoc", "streaming"] = "post_hoc"
    prompt_options: Optional[TranscriptionRequestOptions] = None


class CaseCreateResponse(BaseModel):
    case_id: UUID
    status: str


class AudioChunkResponse(BaseModel):
    chunk_index: int
    status: str


class CaseResponse(BaseModel):
    id: UUID
    status: str
    created_at: datetime
    procedure_type: str
    created_by: str
    scheduled_team: Optional[Dict[str, str]] = None
    ingest_mode: str
    ingest_complete: bool
    needs_review: bool
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    role_map: Optional[Dict[str, Any]] = None
    role_reasoning: Optional[str] = None
    timeline: Optional[Dict[str, Any]] = None
    medications: Optional[List[Any]] = None
    instrument_counts: Optional[List[Any]] = None
    checklist_result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class TranscriptResponse(BaseModel):
    case_id: UUID
    raw_transcript: RawTranscript


class RoleUpdateRequest(BaseModel):
    role_map: Dict[str, str]


class AnalyzeJsonRequest(BaseModel):
    """Raw JSON body for POST /api/v1/analyze (Content-Type: application/json)."""

    audio_base64: str = Field(..., description="Base64-encoded .wav, .mp3, or .m4a audio")
    filename: str = "audio.wav"
    procedure_type: str = ""
    scheduled_team: Optional[Dict[str, str]] = None
    context_type: ContextType = "operating_room"
    attendees: List[AttendeeRole] = Field(
        default_factory=lambda: ["surgeon", "anesthetist", "nurse", "scrub_tech", "resident"]
    )
    purpose: Purpose = "full_transcript_review"
    detail_level: DetailLevel = "standard"


class AnalyzeAudioResponse(BaseModel):
    raw_transcript: RawTranscript
    role_map: Dict[str, SpeakerRoleAssignment]
    role_reasoning: str
    needs_review: bool
    timeline: Optional[TimelineExtractionResult] = None
    checklist: Optional[ChecklistVerificationResult] = None


class ApproveRequest(BaseModel):
    user_id: str


class HealthResponse(BaseModel):
    status: str
    database: str
    details: Dict[str, Any] = Field(default_factory=dict)


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
