"""Pydantic schemas for OCR Parsing Service."""
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


class ExtractTextResponse(BaseModel):
    text_lines: list[str] = Field(default_factory=list, description="OCR extracted text lines")
    line_count: int = Field(..., description="Number of non-empty lines")
    avg_confidence: float | None = Field(
        default=None,
        description="Average OCR confidence in [0,1] when available",
    )


class ParseTextRequest(BaseModel):
    text_lines: list[str] | None = Field(
        default=None,
        description="OCR extracted lines to parse",
    )
    text: str | None = Field(
        default=None,
        description="Raw text to parse if text_lines are not provided",
    )

    @model_validator(mode="after")
    def validate_input(self) -> "ParseTextRequest":
        lines = [line for line in (self.text_lines or []) if line.strip()]
        raw_text = (self.text or "").strip()
        if not lines and not raw_text:
            raise ValueError("Provide either non-empty text_lines or text")
        return self

    def to_raw_text(self) -> str:
        lines = [line.strip() for line in (self.text_lines or []) if line.strip()]
        if lines:
            return "\n".join(lines)
        return (self.text or "").strip()


class ParseTextResponse(BaseModel):
    structured_data: dict[str, Any] = Field(..., description="Parsed structured JSON data")
    model: str = Field(..., description="Model used for parsing")


class ExtractAndParseResponse(BaseModel):
    text_lines: list[str] = Field(default_factory=list, description="OCR extracted text lines")
    structured_data: dict[str, Any] = Field(..., description="Parsed structured JSON data")
    model: str = Field(..., description="Model used for parsing")


class OCRQuality(BaseModel):
    avg_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    low_confidence_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    image_width_px: int | None = Field(default=None, ge=1)
    image_height_px: int | None = Field(default=None, ge=1)
    image_rotation_degrees: int | None = Field(default=None)
    blur_variance: float | None = Field(default=None, ge=0.0, description="Variance of Laplacian (higher is sharper)")
    brightness_mean: float | None = Field(default=None, ge=0.0, le=255.0)
    contrast_std: float | None = Field(default=None, ge=0.0, le=255.0)
    is_low_quality: bool = Field(default=False)
    warnings: list[str] = Field(default_factory=list)


class PatientIdentity(BaseModel):
    full_name: str | None = Field(default=None, description="Full name as printed on document")
    date_of_birth: str | None = Field(default=None, description="ISO date YYYY-MM-DD when available")
    gender: Literal["male", "female", "unspecified"] | None = Field(default=None)
    nationality: str | None = Field(default=None, description="Nationality (prefer 3-letter code if from MRZ)")
    document_number: str | None = Field(default=None)
    document_type: Literal["passport", "id_card", "unknown"] = Field(default="unknown")
    extraction_source: Literal["mrz", "visual", "mrz+visual", "llm_fallback"] = Field(default="visual")


class IdentityIssue(BaseModel):
    field: Literal["full_name", "date_of_birth", "gender", "nationality", "document_number"]
    code: str
    message: str


class IdentityValidation(BaseModel):
    ok: bool = Field(default=True)
    errors: list[IdentityIssue] = Field(default_factory=list)
    warnings: list[IdentityIssue] = Field(default_factory=list)


class IdentityExtractResponse(BaseModel):
    identity: PatientIdentity = Field(...)
    quality: OCRQuality = Field(...)
    validation: IdentityValidation = Field(...)
    mrz_present: bool = Field(default=False)
    mrz_valid: bool | None = Field(default=None, description="MRZ check-digit validation result when MRZ present")
    text_lines: list[str] = Field(default_factory=list, description="OCR extracted text lines (for debugging/audit)")
