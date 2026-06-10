"""Prompt builders for the radiology report filling service."""
import json
from typing import Any, Dict

from app.models.schemas import RadiologyReportRequest
from app.templates.report_templates import ReportTemplate


def build_report_filling_system_prompt(
    guide_text: str,
    schema_text: str,
    output_language: str,
    selected_template: ReportTemplate,
) -> str:
    """System prompt for adapting a stored radiology template."""
    return (
        "You are MedScribe-Template, an assistive AI that adapts stored radiology report templates.\n"
        "You will receive a pre-selected report template plus optional clinical context.\n\n"
        "OUTPUT FORMAT (CRITICAL):\n"
        "- Return ONLY a valid JSON object.\n"
        "- Use ONLY these top-level keys: ID, TEMPLATE_NAME, TEMPLATE_TEXT, STATUS_ID,\n"
        "  CREATED_BY, CREATION_DATETIME, DELETED_BY, DELETE_DATETIME, UPDATED_BY,\n"
        "  UPDATE_DATETIME, Physician.\n"
        "- Put every narrative element inside TEMPLATE_TEXT.\n"
        "- Do NOT return DICOM, OutputLanguage, findings, warnings, summary,\n"
        "  AIInterpretation, QCResult, doctor_notes, radiologist_notes, or any other\n"
        "  separate clinical fields.\n"
        "- Do not invent patient metadata.\n"
        f"- The requested output language is: {output_language}.\n"
        "- TEMPLATE_NAME and TEMPLATE_TEXT must remain in the requested language.\n\n"
        "TEMPLATE ADAPTATION RULES (CRITICAL):\n"
        "- Start from the provided BASE_TEMPLATE_TEXT exactly as the structural foundation.\n"
        "- Preserve the report style, paragraph order, radiology phrasing, headings,\n"
        "  line breaks, and signature block unless clinical context requires a targeted edit.\n"
        "- Integrate only relevant findings from doctor notes, radiologist notes,\n"
        "  AI interpretation, or DICOM metadata into the appropriate paragraphs.\n"
        "- Do NOT replace the template with a short AI summary or generic placeholder text.\n"
        "- Do NOT add generic disclaimers unless the base template already contains them.\n"
        "- If clinical context is insufficient or unrelated, return the base template unchanged.\n"
        "- Do not fabricate unsupported pathology.\n"
        f"- BASE_TEMPLATE_NAME: {selected_template.name}\n"
        f"- BASE_PHYSICIAN: {selected_template.physician or 'null'}\n\n"
        "LANGUAGE RULES:\n"
        "- If output_language is 'el', keep Greek radiology prose.\n"
        "- If output_language is 'pt', keep Portuguese radiology prose.\n"
        "- If output_language is 'en', keep English radiology prose.\n"
        "- If output_language is 'ar', keep Arabic radiology prose.\n"
        "- Keep JSON keys in English exactly as required by the schema.\n\n"
        "--- DOMAIN GUIDE ---\n"
        f"{guide_text}\n\n"
        "--- RESPONSE SHAPE REFERENCE ---\n"
        f"{schema_text}\n"
    )


def build_report_filling_user_prompt(
    payload: RadiologyReportRequest,
    resolved_context: Dict[str, Any],
    output_language: str,
    selected_template: ReportTemplate,
) -> str:
    """User prompt for adapting a stored radiology template."""
    metadata: Dict[str, Any] = payload.model_dump(mode="json")
    clinical_context = {
        "ExamType": payload.ExamType,
        "DoctorNotes": payload.DoctorNotes,
        "RadiologistNotes": payload.RadiologistNotes,
        "AIInterpretation": payload.AIInterpretation,
        "QCResult": payload.QCResult,
    }
    return (
        "REPORT FILLING REQUEST:\n\n"
        f"OUTPUT_LANGUAGE: {output_language}\n\n"
        "BASE_TEMPLATE:\n"
        f"TEMPLATE_NAME: {selected_template.name}\n"
        f"TEMPLATE_TEXT:\n{selected_template.text}\n\n"
        "PATIENT_AND_ORDER_METADATA:\n"
        f"{json.dumps(metadata, indent=2)}\n\n"
        "CLINICAL_CONTEXT:\n"
        f"{json.dumps(clinical_context, indent=2, default=str)}\n\n"
        "RESOLVED_TEMPLATE_CONTEXT:\n"
        f"{json.dumps(resolved_context, indent=2, default=str)}\n\n"
        "INSTRUCTION:\n"
        "Adapt the BASE_TEMPLATE using only relevant clinical context. Return one JSON object\n"
        "with the required response keys only. Keep the full template-style report body inside\n"
        "TEMPLATE_TEXT and preserve line breaks."
    )
