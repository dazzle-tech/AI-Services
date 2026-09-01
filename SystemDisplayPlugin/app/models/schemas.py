"""Pydantic request/response schemas."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

# Same enums as ORScribe/ConvoScribe app.ai.unified_prompts (copied, not imported:
# this service is self-contained).
ContextType = Literal[
    "appointment",
    "ward_round",
    "operating_room",
    "procedure",
    "telehealth",
    "other",
]

Purpose = Literal[
    "summary",
    "soap_note",
    "clinical_document",
    "timeline",
    "checklist_verification",
    "full_transcript_review",
]

FieldType = Literal["string", "list", "boolean", "object", "date"]
TransformType = Literal["direct", "summarize", "concat", "split", "extract"]


class DecoderField(BaseModel):
    field_name: str
    field_type: FieldType
    source_path: str
    transform: TransformType = "direct"
    transform_hint: Optional[str] = None
    required: bool = True


class ViewDecoder(BaseModel):
    view_id: str
    view_name: str
    fields: List[DecoderField]


class ReshapeRequest(BaseModel):
    stage1_output: Dict[str, Any]
    context: ContextType
    purpose: Purpose
    view_decoder: Optional[ViewDecoder] = None
    view_id: Optional[str] = None

    @model_validator(mode="after")
    def require_decoder_or_id(self) -> "ReshapeRequest":
        if self.view_decoder is None and not self.view_id:
            raise ValueError("Provide view_decoder (inline) or view_id (stored)")
        return self


class ReshapeResponse(BaseModel):
    view_id: str
    data: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
    details: Dict[str, Any] = Field(default_factory=dict)
