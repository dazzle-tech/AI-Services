"""
Pydantic schemas for the Radiology Template Selection & Autofill Service.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SelectionMethod(str, Enum):
    RAG = "rag"
    STATIC = "static"


class TemplateField(BaseModel):
    name: str = Field(..., description="Internal field key, e.g. 'findings.lungs'.")
    label: str = Field(..., description="Human-readable section/field label.")
    description: Optional[str] = Field(
        None, description="Guidance for the LLM on what to populate."
    )
    required: bool = Field(False, description="If true, missing values are flagged.")


class Template(BaseModel):
    template_id: str
    name: str
    modality: str = Field(..., description="CT, MRI, US, X-ray, Mammography, etc.")
    body_region: Optional[str] = Field(None, description="Chest, Abdomen, Brain, etc.")
    description: str = Field(..., description="Used for RAG embedding context.")
    keywords: list[str] = Field(default_factory=list)
    fields: list[TemplateField]


class TemplateSummary(BaseModel):
    template_id: str
    name: str
    modality: str
    body_region: Optional[str] = None
    description: str


class TemplateCandidate(BaseModel):
    template_id: str
    name: str
    modality: str
    body_region: Optional[str] = None
    score: float = Field(..., description="Higher = better match (cosine similarity).")


# --- Selection ----------------------------------------------------------------

class SelectTemplateRequest(BaseModel):
    request_id: Optional[str] = None
    input_data: str = Field(..., min_length=1, description="Raw clinician input / dictation.")
    use_static_template: bool = Field(
        False, description="If true, bypass RAG and force `static_template_id`."
    )
    static_template_id: Optional[str] = Field(
        None, description="Required when use_static_template=true."
    )
    top_k: int = Field(3, ge=1, le=10, description="Number of RAG candidates to consider.")


class SelectTemplateResponse(BaseModel):
    request_id: Optional[str] = None
    selection_method: SelectionMethod
    selected_template_id: str
    selected_template_name: str
    intent_profile: Optional[str] = Field(
        None, description="Brief modality/region intent extracted from input."
    )
    candidates: list[TemplateCandidate] = Field(default_factory=list)
    selection_timestamp: datetime = Field(default_factory=datetime.utcnow)


# --- Autofill -----------------------------------------------------------------

class AutofillRequest(BaseModel):
    request_id: Optional[str] = None
    template_id: str = Field(..., description="ID of the template to populate.")
    input_data: str = Field(..., min_length=1, description="Raw input to map into the template.")
    patient_context: Optional[dict[str, Any]] = Field(
        None, description="Optional patient metadata to enrich autofill."
    )


class FieldValidation(BaseModel):
    field_name: str
    issue: str
    severity: str = Field("warning", description="info | warning | error")


class AutofillResponse(BaseModel):
    request_id: Optional[str] = None
    template_id: str
    template_name: str
    populated_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Map of field_name -> generated value (string or list).",
    )
    rendered_report: str = Field(..., description="Final report as plain text.")
    missing_required_fields: list[str] = Field(default_factory=list)
    warnings: list[FieldValidation] = Field(default_factory=list)
    confidence_score: float = Field(0.0, ge=0.0, le=1.0)
    generation_timestamp: datetime = Field(default_factory=datetime.utcnow)


# --- Combined select + fill ---------------------------------------------------

class SelectAndFillRequest(BaseModel):
    request_id: Optional[str] = None
    input_data: str = Field(..., min_length=1)
    use_static_template: bool = False
    static_template_id: Optional[str] = None
    top_k: int = Field(3, ge=1, le=10)
    patient_context: Optional[dict[str, Any]] = None


class SelectAndFillResponse(BaseModel):
    request_id: Optional[str] = None
    selection: SelectTemplateResponse
    autofill: AutofillResponse
