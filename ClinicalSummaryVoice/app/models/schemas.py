"""Pydantic schemas for ClinicalSummaryVoice."""

from typing import Any, Dict

from pydantic import BaseModel, Field


class SummarizeJsonRequest(BaseModel):
    audio_base64: str
    filename: str = "audio.wav"


class SummaryResponse(BaseModel):
    summary: str
    transcript: str


class HealthResponse(BaseModel):
    status: str
    details: Dict[str, Any] = Field(default_factory=dict)
