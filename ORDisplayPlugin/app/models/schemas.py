"""Pydantic request/response schemas."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

# Same enums as ORScribe app.ai.unified_prompts (copied, not imported:
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
    context: ContextType = "operating_room"
    purpose: Purpose = "timeline"
    views: Optional[List[ViewDecoder]] = None
    view_ids: Optional[List[str]] = None
    # Backward-compatible single-view aliases
    view_decoder: Optional[ViewDecoder] = None
    view_id: Optional[str] = None

    @model_validator(mode="after")
    def require_views_or_ids(self) -> "ReshapeRequest":
        has_inline = bool(self.views) or self.view_decoder is not None
        has_ids = bool(self.view_ids) or bool(self.view_id)
        if not has_inline and not has_ids:
            raise ValueError("Provide views/view_decoder and/or view_ids/view_id")
        return self

    def collected_inline_views(self) -> List[ViewDecoder]:
        items: List[ViewDecoder] = list(self.views or [])
        if self.view_decoder is not None:
            items.append(self.view_decoder)
        return items

    def collected_view_ids(self) -> List[str]:
        items: List[str] = list(self.view_ids or [])
        if self.view_id:
            items.append(self.view_id)
        return items


class ViewResult(BaseModel):
    view_id: str
    data: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)


class ReshapeResponse(BaseModel):
    results: List[ViewResult]


class HealthResponse(BaseModel):
    status: str
    database: str
    details: Dict[str, Any] = Field(default_factory=dict)
