"""Prompt builders for Medical Imaging Assist.

These are pure functions: they take pre-loaded text (guide, schema, RAG
candidates) and produce prompt strings. They do NOT read files or call
configuration.
"""
import json
from typing import Any, Dict, List


_COMMON_RULES = (
    "OUTPUT FORMAT (CRITICAL):\n"
    "- Return ONLY a valid JSON object. No markdown, no code fences, no commentary.\n"
    "- Return the INNER content fields directly at the TOP LEVEL of your JSON.\n"
    "- DO NOT wrap your response in 'raw_model_output', 'safety_normalized_output',\n"
    "  or 'disclaimer' keys. The service adds those layers itself.\n"
    "- DO NOT include 'confidence', 'priority', or 'critical_alert' keys.\n"
    "  The deterministic safety normalizer assigns those, not you.\n"
    "- Do not invent ICD-10 codes or RadLex IDs. Choose only from the candidate list below.\n"
    "- If no candidate matches, return an empty list for that category.\n"
)


_CONTENT_FIELD_GUIDE = (
    "INNER CONTENT FIELDS (return these at the top level of your JSON):\n"
    "- study_metadata: object (echo the DICOM tags you saw)\n"
    "- exam_type: string\n"
    "- findings: array of {label, location?, status?, size_cm?, source}\n"
    "    where source in ['doctor','radiologist','clinical_report','ai','reconciled']\n"
    "- warnings: array of {severity in ['info','high','critical'], code, message}\n"
    "- rag_grounding: { icd10_codes: [{code, term, matched_phrase}], "
    "radlex_terms: [{id, term, matched_phrase}] }\n"
)


def _format_candidates(candidates: List[Dict[str, Any]], kind: str) -> str:
    """Render the RAG candidate list as a compact JSON block for the prompt."""
    if not candidates:
        return f"(no {kind} candidates retrieved)"
    slim = []
    for c in candidates:
        if kind == "icd10":
            slim.append({"code": c["code"], "term": c["term"], "matched_phrase": c.get("matched_phrase", "")})
        else:
            slim.append({"id": c["id"], "term": c["term"], "matched_phrase": c.get("matched_phrase", "")})
    return json.dumps(slim, indent=2)


def build_correction_system_prompt(
    guide_text: str,
    schema_text: str,
    icd10_candidates: List[Dict[str, Any]],
    radlex_candidates: List[Dict[str, Any]],
) -> str:
    """System prompt for /api/v1/report-correction."""
    return (
        "You are MedScribe-Reviewer, an assistive AI that helps radiologists clean up reports.\n"
        "You will receive a doctor's clinical note, a radiologist's read, an optional exam_type,\n"
        "and DICOM metadata. You must:\n\n"
        "TASKS:\n"
        "1. Fix misspellings in both notes (e.g., cardimegaly -> cardiomegaly,\n"
        "   effuzion -> effusion, costofrenic -> costophrenic).\n"
        "2. Expand clinical shorthand (e.g., SOB -> shortness of breath, hx -> history,\n"
        "   C/o -> complains of, R/o -> rule out, RML -> right middle lobe).\n"
        "3. Cross-reference the two notes for CONFLICTS. The most important conflict to\n"
        "   detect is LATERALITY: if one note says 'left' and the other says 'right' for\n"
        "   the same anatomic region, this is a high-severity warning.\n"
        "4. Build a structured_report dict with sections:\n"
        "   indication, technique, findings (array of objects), impression.\n"
        "5. From the provided ICD-10 and RadLex CANDIDATES below, pick the ones whose\n"
        "   `matched_phrase` actually appears in the input (or is clinically implied).\n"
        "   Return them in `rag_grounding`. Do not invent codes.\n"
        "6. Return a `spelling_corrections` mapping {wrong: corrected, ...}.\n\n"
        "WARNING CODES YOU MAY EMIT (the normalizer may add more):\n"
        "  LATERALITY_CONFLICT, SHORTHAND_EXPANDED, SPELLING_CORRECTED\n\n"
        f"{_COMMON_RULES}\n"
        f"{_CONTENT_FIELD_GUIDE}\n"
        "Additional inner fields for THIS endpoint:\n"
        "- corrected_doctor_notes: string\n"
        "- corrected_radiologist_notes: string\n"
        "- structured_report: { indication, technique, findings, impression }\n"
        "- spelling_corrections: { wrong_word: corrected_word, ... }\n\n"
        "--- DOMAIN GUIDE ---\n"
        f"{guide_text}\n\n"
        "--- FULL ENVELOPE REFERENCE (FOR YOUR AWARENESS ONLY -- "
        "you return ONLY the inner content, not this envelope) ---\n"
        f"{schema_text}\n\n"
        "--- ICD-10 CANDIDATES (choose from these only) ---\n"
        f"{_format_candidates(icd10_candidates, 'icd10')}\n\n"
        "--- RADLEX CANDIDATES (choose from these only) ---\n"
        f"{_format_candidates(radlex_candidates, 'radlex')}\n"
    )


def build_correction_user_prompt(
    doctor_notes: str,
    radiologist_notes: str,
    exam_type: str | None,
    dicom_metadata: Dict[str, Any],
) -> str:
    """User prompt for /api/v1/report-correction."""
    return (
        "REPORT CORRECTION REQUEST:\n\n"
        f"DOCTOR_NOTES:\n{doctor_notes}\n\n"
        f"RADIOLOGIST_NOTES:\n{radiologist_notes}\n\n"
        f"EXAM_TYPE: {exam_type or '(not provided)'}\n\n"
        "DICOM_METADATA:\n"
        f"{json.dumps(dicom_metadata, indent=2)}\n\n"
        "INSTRUCTION: Produce a single JSON object with keys: corrected_doctor_notes,\n"
        "corrected_radiologist_notes, structured_report, spelling_corrections, findings,\n"
        "warnings, rag_grounding (with icd10_codes and radlex_terms), study_metadata,\n"
        "exam_type. Do not include `confidence`, `priority`, `critical_alert`, or\n"
        "`disclaimer`; the service assigns those."
    )


def build_matching_system_prompt(
    guide_text: str,
    schema_text: str,
    icd10_candidates: List[Dict[str, Any]],
    radlex_candidates: List[Dict[str, Any]],
) -> str:
    """System prompt for /api/v1/analysis-matching."""
    return (
        "You are MedScribe-Reconciler, an assistive AI that reconciles a finalized\n"
        "clinical_report (AUTHORITATIVE) with an AI image analysis result (assistive).\n\n"
        "HIERARCHY OF TRUTH (NON-NEGOTIABLE):\n"
        "If the AI image analysis disagrees with the clinical_report on any measurable\n"
        "or categorical fact -- size, laterality, presence/absence, location -- the\n"
        "clinical_report wins. Record the AI's value under `ai_variance` for that finding\n"
        "and add an AI_SIZE_VARIANCE (or appropriate) warning. The AI value MUST NOT\n"
        "replace the doctor's value in `findings`.\n\n"
        "TASKS:\n"
        "1. Build `reconciled_findings`: an array where each finding has\n"
        "   {label, location, size_cm | size_mm, source, [ai_variance]}.\n"
        "2. Build `ai_findings_dropped`: AI findings that contradicted the clinical_report.\n"
        "3. Build `ai_findings_used_for_enrichment`: AI findings that added\n"
        "   non-conflicting detail (e.g., 'right 5th rib, posterior segment' when\n"
        "   the doctor only said 'right rib fracture').\n"
        "4. Detect anatomy/metadata mismatch: if DICOM BodyPartExamined disagrees with the\n"
        "   anatomy described in the clinical_report or the AI's detected_anatomy, emit\n"
        "   an ANATOMY_METADATA_MISMATCH warning of severity 'critical'.\n"
        "5. Populate `rag_grounding` from the candidates below; do not invent codes.\n\n"
        "WARNING CODES YOU MAY EMIT (normalizer may add more):\n"
        "  AI_SIZE_VARIANCE, ANATOMY_METADATA_MISMATCH, AI_FINDING_DROPPED,\n"
        "  AI_ENRICHMENT_APPLIED, SINGLE_VIEW_LIMITATION\n\n"
        f"{_COMMON_RULES}\n"
        f"{_CONTENT_FIELD_GUIDE}\n"
        "Additional inner fields for THIS endpoint:\n"
        "- reconciled_findings: array of {label, location, size_cm, source='clinical_report', "
        "ai_variance?: {ai_size_mm, delta_mm, note}}\n"
        "- ai_findings_dropped: array (AI findings that contradicted the clinical_report)\n"
        "- ai_findings_used_for_enrichment: array (AI findings that added non-conflicting "
        "detail used to enrich the report)\n\n"
        "--- DOMAIN GUIDE ---\n"
        f"{guide_text}\n\n"
        "--- FULL ENVELOPE REFERENCE (FOR YOUR AWARENESS ONLY -- "
        "you return ONLY the inner content, not this envelope) ---\n"
        f"{schema_text}\n\n"
        "--- ICD-10 CANDIDATES (choose from these only) ---\n"
        f"{_format_candidates(icd10_candidates, 'icd10')}\n\n"
        "--- RADLEX CANDIDATES (choose from these only) ---\n"
        f"{_format_candidates(radlex_candidates, 'radlex')}\n"
    )


def build_matching_user_prompt(
    clinical_report: str,
    ai_image_analysis: Dict[str, Any],
    dicom_metadata: Dict[str, Any],
) -> str:
    """User prompt for /api/v1/analysis-matching."""
    return (
        "ANALYSIS MATCHING REQUEST:\n\n"
        f"CLINICAL_REPORT (AUTHORITATIVE):\n{clinical_report}\n\n"
        "AI_IMAGE_ANALYSIS (assistive only):\n"
        f"{json.dumps(ai_image_analysis, indent=2)}\n\n"
        "DICOM_METADATA:\n"
        f"{json.dumps(dicom_metadata, indent=2)}\n\n"
        "INSTRUCTION: Produce a single JSON object with keys: reconciled_findings,\n"
        "ai_findings_dropped, ai_findings_used_for_enrichment, findings (final list,\n"
        "source=reconciled), warnings, rag_grounding, study_metadata, exam_type.\n"
        "Do not include `confidence`, `priority`, `critical_alert`, or `disclaimer`;\n"
        "the service assigns those."
    )
