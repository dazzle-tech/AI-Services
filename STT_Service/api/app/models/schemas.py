"""Pydantic request/response schemas."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class TranscriptionSegment(BaseModel):
    id: int
    start: float
    end: float
    text: str
    avg_logprob: float
    no_speech_prob: float


class TranscriptionResponse(BaseModel):
    request_id: Optional[str] = None
    text: str = Field(..., description="Full transcribed text (post-processed for radiology terminology).")
    raw_text: Optional[str] = Field(None, description="Pre-postprocessing text (for debugging).")
    language: str
    language_probability: float
    audio_duration_seconds: float
    inference_seconds: float
    segments: List[TranscriptionSegment] = []
    model: str
    device: str


class HealthResponse(BaseModel):
    status: str
    service: str = "stt-radiology"
    version: str = "1.0.0"
    model: str
    device: str
    compute_type: str
    radiology_prompt_loaded: bool
    ffmpeg_available: bool


class ServiceInfoResponse(BaseModel):
    service: str = "stt-radiology"
    description: str = "Specialized Speech-to-Text for Radiology (local Whisper)"
    version: str = "1.0.0"
    endpoints: dict


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    request_id: Optional[str] = None


# --- WebSocket message schemas (documentation only; not strictly enforced) ----

class WSClientControl(BaseModel):
    """Control messages a client may send (as JSON text frames) over the WebSocket.

    Example:
        {"type": "start", "sample_rate": 16000, "channels": 1,
         "language": "en", "extra_prompt": "patient is 45M, chest CT"}
        {"type": "stop"}
    """
    type: str
    sample_rate: Optional[int] = 16000
    channels: Optional[int] = 1
    language: Optional[str] = None
    extra_prompt: Optional[str] = None


class WSPartialMessage(BaseModel):
    type: str = "partial"
    text: str = Field(..., description="Rolling transcript accumulated across all windows so far.")
    raw_text: Optional[str] = None
    window_text: Optional[str] = Field(None, description="Transcription of just the most recent window.")
    audio_seconds_processed: float
    inference_seconds: float


class WSFinalMessage(BaseModel):
    type: str = "final"
    text: str
    raw_text: Optional[str] = None
    audio_seconds: float
    segments: List[TranscriptionSegment] = []
