"""
Pydantic schemas for the Radiology Template Selection & Autofill Service.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

_SUPPORTED_OUTPUT_LANGUAGES = {"el", "pt", "en", "ar"}


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


class OutputLanguageRequestMixin(BaseModel):
    OutputLanguage: Optional[str] = Field(
        "el",
        description="Language code for the generated report text. Examples: el, pt, en, ar.",
    )

    @field_validator("OutputLanguage", mode="before")
    @classmethod
    def validate_output_language(cls, value: Optional[str]) -> str:
        if value in (None, ""):
            return "el"
        normalized = str(value).strip().lower()
        if normalized not in _SUPPORTED_OUTPUT_LANGUAGES:
            supported = ", ".join(sorted(_SUPPORTED_OUTPUT_LANGUAGES))
            raise ValueError(f"OutputLanguage must be one of: {supported}")
        return normalized


# --- Selection ----------------------------------------------------------------

class SelectTemplateRequest(OutputLanguageRequestMixin):
    request_id: Optional[str] = None
    input_data: str = Field(..., min_length=1, description="Raw clinician input / dictation.")
    use_static_template: bool = Field(
        False, description="If true, bypass RAG and force `static_template_id`."
    )
    static_template_id: Optional[str] = Field(
        None, description="Required when use_static_template=true."
    )
    top_k: int = Field(3, ge=1, le=10, description="Number of RAG candidates to consider.")
    patient_context: Optional[dict[str, Any]] = Field(
        None, description="Optional patient metadata to constrain selection."
    )


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

class AutofillRequest(OutputLanguageRequestMixin):
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


class RadiologyTemplateResponse(BaseModel):
    ID: int
    TEMPLATE_NAME: str
    TEMPLATE_TEXT: str
    STATUS_ID: Optional[int] = None
    CREATED_BY: Optional[str] = None
    CREATION_DATETIME: Optional[datetime] = None
    DELETED_BY: Optional[str] = None
    DELETE_DATETIME: Optional[datetime] = None
    UPDATED_BY: Optional[str] = None
    UPDATE_DATETIME: Optional[datetime] = None
    Physician: Optional[str] = None


class AutofillResponse(RadiologyTemplateResponse):
    pass


# --- Combined select + fill ---------------------------------------------------

class SelectAndFillRequest(OutputLanguageRequestMixin):
    request_id: Optional[str] = None
    input_data: str = Field(..., min_length=1)
    use_static_template: bool = False
    static_template_id: Optional[str] = None
    top_k: int = Field(3, ge=1, le=10)
    patient_context: Optional[dict[str, Any]] = None


class SelectAndFillResponse(RadiologyTemplateResponse):
    pass
