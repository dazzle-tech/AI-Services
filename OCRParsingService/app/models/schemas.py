"""Pydantic schemas for OCR Parsing Service."""
from typing import Any
from pydantic import BaseModel, Field, model_validator


class ExtractTextResponse(BaseModel):
    text_lines: list[str] = Field(default_factory=list, description="OCR extracted text lines")
    line_count: int = Field(..., description="Number of non-empty lines")


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
