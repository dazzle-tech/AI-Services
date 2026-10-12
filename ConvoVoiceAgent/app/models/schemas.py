"""Pydantic schemas for ConvoVoiceAgent."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AnalyzeJsonRequest(BaseModel):
    audio_base64: str
    filename: str = "audio.wav"
    context_type: str = "appointment"
    purpose: str = "soap_note"
    detail_level: str = "standard"
    view_ids: Optional[List[str]] = None


class ViewResult(BaseModel):
    view_id: str
    data: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    """SystemDisplayPlugin reshape body — the caller's final payload."""

    results: List[ViewResult]


class DownstreamHealth(BaseModel):
    convoscribe: str
    system_display_plugin: str


class HealthResponse(BaseModel):
    status: str
    downstream: DownstreamHealth
    details: Dict[str, Any] = Field(default_factory=dict)
