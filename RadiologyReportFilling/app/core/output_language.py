"""Output language helpers for user-facing text."""
from typing import Literal, Optional

OutputLanguage = Literal["en", "el"]

_OUTPUT_LANGUAGE_INSTRUCTION = (
    "Return all user-facing text in the requested output_language. "
    "If output_language is 'el', write the report, findings, warnings, corrected notes, "
    "and impression in Greek. Keep JSON keys, ICD-10 codes, RadLex IDs, DICOM tags, "
    "and internal warning codes unchanged."
)


def language_prompt_block(output_language: Optional[OutputLanguage]) -> str:
    """Prompt fragment for the LLM; empty when output_language is omitted."""
    if output_language is None:
        return ""
    return (
        f"\nOUTPUT LANGUAGE: {output_language}\n"
        f"{_OUTPUT_LANGUAGE_INSTRUCTION}\n"
    )


def unspecified_exam_type(output_language: Optional[OutputLanguage]) -> str:
    """Default exam_type label when none is provided."""
    if output_language == "el":
        return "Ακαθόριστο"
    return "Unspecified"
