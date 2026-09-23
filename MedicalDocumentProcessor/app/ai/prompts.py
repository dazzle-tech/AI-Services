"""Prompt templates for the Medical Document Processor pipeline.

Four separate, clearly-scoped prompts -- one per pipeline step -- so each step is
independently testable and debuggable, per the pipeline design. None of these prompts
are combined into a single call.
"""
import json
from typing import Any, Dict, List, Optional

from app.models.schemas import DocumentType


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]"


# ---------------------------------------------------------------------------
# Step 1 -- patient-match validation
# ---------------------------------------------------------------------------
def build_validation_prompt(
    patient: Dict[str, Any], extracted_text: str, max_chars: int
) -> List[Dict[str, str]]:
    schema = {
        "is_valid": "boolean -- true only if no clear contradiction was found",
        "extracted_patient_signals": {
            "full_name": "string|null -- name found in the document, if any",
            "sex": "male|female|unspecified|null -- sex/gender found in the document, if any",
            "date_of_birth": "string|null -- ISO date found in the document, if any",
            "patient_id": "string|null -- patient/MRN identifier found in the document, if any",
        },
        "mismatches": ["string -- one entry per specific contradiction found"],
        "reason": "string|null -- short human-readable summary, required when is_valid is false",
    }

    system = f"""You are a clinical document intake validator. Your ONLY job is to check
whether a medical document appears to belong to the patient it was uploaded for.

Extract any patient-identifying signals present in the document text (full name, sex/gender,
date of birth, patient ID/MRN -- whatever is present) and compare them against the given
patient record. Flag a mismatch ONLY when there is a clear, specific contradiction (e.g. the
document states the patient is male but the record says female; or the document's date of
birth clearly differs from the record's; or the name is clearly a different person).

Do NOT flag a mismatch merely because a signal is absent from the document -- absence of
information is not a contradiction. Be conservative: only report mismatches you are confident
about, and always state the concrete conflicting values in "mismatches".

Return STRICT JSON only. No markdown, no code fences, no extra text before or after the JSON
object. The output must be one JSON object with this exact top-level structure:
{json.dumps(schema, indent=2)}
"""

    user = f"""PATIENT RECORD (given at upload time):
{json.dumps(patient, indent=2, default=str)}

DOCUMENT TEXT (extracted from the uploaded file):
{_truncate(extracted_text, max_chars)}

Compare the document against the patient record and return ONLY the required JSON object."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Step 2 -- relevance classification
# ---------------------------------------------------------------------------
def build_relevance_prompt(
    extracted_text: str,
    relevance_windows_days: Dict[str, int],
    existing_documents: List[Dict[str, Any]],
    max_chars: int,
) -> List[Dict[str, str]]:
    schema = {
        "apparent_document_type": f"one of {DocumentType.values()}",
        "document_date": "string|null -- ISO date the document pertains to, if determinable",
        "is_relevant": "boolean",
        "reason": (
            "string -- required, specific reason. When not relevant, state the document type, "
            "its date, and the relevance window that was exceeded, or which existing document "
            "supersedes it."
        ),
    }

    windows_text = "\n".join(
        f"  - {doc_type}: {days} days" for doc_type, days in relevance_windows_days.items()
    )
    existing_text = (
        json.dumps(existing_documents, indent=2, default=str)
        if existing_documents
        else "None provided."
    )

    system = f"""You are a clinical document relevance classifier. Your job is to decide
whether a newly uploaded document is still clinically relevant to include in a patient's
ACTIVE record, using this rubric:

1. Identify the document's apparent type (one of {DocumentType.values()}) and the date it
   pertains to (e.g. test date, study date, note date -- not the upload date).
2. Compare the document's age against the configured relevance window for its type (in days):
{windows_text}
   If the document is older than its type's window, it is NOT relevant (outdated/superseded).
3. If a newer existing document of the SAME type is listed below, the newly uploaded document
   is superseded and is NOT relevant, even if it is within the recency window.
4. A document type that plainly does not apply to active care (e.g. an unrelated administrative
   form) is NOT relevant.
5. If the document has no determinable date, be conservative and treat it as relevant unless
   there is a clear reason otherwise (e.g. explicitly superseded).

Return STRICT JSON only. No markdown, no code fences, no extra text before or after the JSON
object. The output must be one JSON object with this exact top-level structure:
{json.dumps(schema, indent=2)}
"""

    user = f"""EXISTING DOCUMENTS ALREADY ON RECORD (for supersede checks):
{existing_text}

DOCUMENT TEXT (extracted from the uploaded file):
{_truncate(extracted_text, max_chars)}

Classify relevance and return ONLY the required JSON object."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Step 3 -- language detection + conditional translation
# ---------------------------------------------------------------------------
def build_translation_prompt(
    extracted_text: str,
    translate_requested: bool,
    target_language: str,
    max_chars: int,
) -> List[Dict[str, str]]:
    schema = {
        "detected_language": "ISO 639-1 language code (e.g. 'en', 'ar', 'fr') of the document",
        "translated_text": (
            "string|null -- full translation into the target language, or null if no "
            "translation was requested or needed"
        ),
    }

    translate_instruction = (
        f"Translation WAS requested. If detected_language differs from the target language "
        f"'{target_language}', translate the FULL document text into '{target_language}' and "
        f"return it in translated_text. If the document is already in '{target_language}', "
        f"set translated_text to null (no translation needed)."
        if translate_requested
        else "Translation was NOT requested. Always set translated_text to null, regardless "
        "of the detected language."
    )

    system = f"""You are a medical translation and language-detection assistant.

First, detect the primary language of the document text.

{translate_instruction}

When you DO translate, this is a clinical translation, not a casual one:
- Preserve all clinical/medical terminology as precisely as possible.
- Preserve units, dosages, lab values, and all numeric values EXACTLY as written -- never
  convert units or round numbers.
- Preserve document structure (headings, line breaks, list items) as closely as practical.
- Do not omit, summarize, or add information that is not in the source text.

Return STRICT JSON only. No markdown, no code fences, no extra text before or after the JSON
object. The output must be one JSON object with this exact top-level structure:
{json.dumps(schema, indent=2)}
"""

    user = f"""TARGET LANGUAGE: {target_language}
TRANSLATION REQUESTED: {translate_requested}

DOCUMENT TEXT:
{_truncate(extracted_text, max_chars)}

Return ONLY the required JSON object."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Step 4 -- document-type classification + loose structured extraction
# ---------------------------------------------------------------------------
def build_classification_prompt(
    extracted_text: str, max_chars: int
) -> List[Dict[str, str]]:
    schema = {
        "document_type": f"one of {DocumentType.values()}",
        "extracted_fields": (
            "object -- flexible key/value extraction of whatever structured fields are "
            "present and relevant to the classified document_type (e.g. for a lab_result: "
            "test_date, ordering_provider, results (array of {test_name, value, unit, "
            "reference_range, flag}); for a radiology_report: study_date, modality, "
            "body_part_examined, ordering_provider, findings, impression; for a prescription: "
            "prescription_date, prescribing_provider, medications (array of {name, dosage, "
            "frequency, route, duration, instructions}); for a clinical_note/physician_note: "
            "note_date, author, note_type, subjective, objective, assessment, plan). Use null "
            "for any field that cannot be determined from the text -- never invent values."
        ),
    }

    system = f"""You are a clinical document classification and structured-extraction
assistant. Classify the document into exactly one of these types:
{DocumentType.values()}

Then extract the fields relevant to that type into extracted_fields, using only information
present in the document text. Never fabricate values -- use null for anything not present.
Preserve numeric values, units, and dates exactly as written.

Return STRICT JSON only. No markdown, no code fences, no extra text before or after the JSON
object. The output must be one JSON object with this exact top-level structure:
{json.dumps(schema, indent=2)}
"""

    user = f"""DOCUMENT TEXT:
{_truncate(extracted_text, max_chars)}

Classify and extract, then return ONLY the required JSON object."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
