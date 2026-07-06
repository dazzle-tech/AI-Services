from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

DISCLAIMER_TEXT = "Assistive AI only. Radiologist review required. Not for final diagnosis."


class Finding(BaseModel):
    """A single candidate finding identified by the AI."""

    finding_code: str = Field(description="Standardised SNAKE_UPPER_CASE finding identifier.")
    finding_text: str = Field(description="One-sentence plain-English description.")
    location: str | None = Field(default=None, description="Anatomical location.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence 0–1.")
    priority: str = Field(
        ...,
        pattern="^(CRITICAL|URGENT|ROUTINE)$",
        description="CRITICAL=life-threatening, URGENT=prompt attention, ROUTINE=review.",
    )
    radiologist_review_required: bool = Field(default=True)


class StudyInfo(BaseModel):
    """Structured DICOM metadata for the submitted study."""

    study_instance_uid: str | None = None
    modality: str | None = None
    body_part: str | None = None
    laterality: str | None = Field(default=None, description="LEFT, RIGHT, or null.")
    view: str | None = Field(default=None, description="AP, PA, LATERAL, AXIAL, etc.")
    study_description: str | None = None
    series_description: str | None = None
    patient_age: str | None = None
    patient_sex: str | None = None
    image_quality: str | None = Field(default=None, description="ADEQUATE or LIMITED.")


class AIInfo(BaseModel):
    """Which AI model processed this study."""

    model_name: str
    modality_handled: str  # "XRAY" or "CT"
    slices_reviewed: int = 1  # always 1 for X-ray; N for CT
    not_for_medical_use: bool = True


class InterpretationResponse(BaseModel):
    """
    Top-level response from the Medical Image Interpretation Assist Service.
    All fields except `warnings` are always present.
    """

    # --- Identity ---
    exam_type: str = Field(description="e.g. XR_SHOULDER, CT_CHEST")
    status: str = Field(..., pattern="^(COMPLETED|REVIEW_REQUIRED|UNSUPPORTED_MODALITY)$")

    # --- Alert ---
    critical_alert: bool = Field(
        default=False,
        description="True only when at least one CRITICAL finding is present. "
        "Triggers immediate notification in downstream systems.",
    )

    # --- Clinical output ---
    findings: list[Finding] = Field(default_factory=list)
    incidental_or_off_target_findings: list[Finding] = Field(default_factory=list)
    summary: str = Field(description="Plain-English summary of AI findings.")

    # --- Study context ---
    study: StudyInfo = Field(default_factory=StudyInfo)

    # --- AI provenance ---
    ai: AIInfo

    # --- Operational ---
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal issues (mismatch, missing views, image quality).",
    )
    disclaimer: str = Field(default=DISCLAIMER_TEXT)
