"""Prompt builders for the radiology report filling service."""
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
        "- Return valid JSON only. Do not use markdown. Do not include explanations. "
        "Escape all newline characters and quotes correctly.\n"
        "- Use ONLY these top-level keys: ID, TEMPLATE_NAME, TEMPLATE_TEXT, STATUS_ID,\n"
        "  CREATED_BY, CREATION_DATETIME, DELETED_BY, DELETE_DATETIME, UPDATED_BY,\n"
        "  UPDATE_DATETIME, Physician.\n"
        "- Put every narrative element inside TEMPLATE_TEXT.\n"
        "- Do NOT return DICOM, OutputLanguage, findings, warnings, summary,\n"
        "  AIInterpretation, AIInterpretationSummary, QC, QCResult, doctor_notes,\n"
        "  radiologist_notes, or any other\n"
        "  separate clinical fields.\n"
        "- Do not invent patient metadata.\n"
        f"- The requested output language is: {output_language}.\n"
        "- TEMPLATE_NAME and TEMPLATE_TEXT must remain in the requested language.\n\n"
        "TEMPLATE ADAPTATION RULES (CRITICAL):\n"
        "- Start from the provided BASE_TEMPLATE_TEXT exactly as the structural foundation.\n"
        "- Preserve the report style, paragraph order, radiology phrasing, headings,\n"
        "  line breaks, and signature block unless clinical context requires a targeted edit.\n"
        "- RadiologistNotes are the primary source of truth for imaging findings.\n"
        "- DoctorNotes are clinical context only and must not override imaging findings or laterality/location from RadiologistNotes.\n"
        "- If DoctorNotes and RadiologistNotes conflict, follow RadiologistNotes for imaging location and finding.\n"
        "- AIInterpretationSummary is secondary context only and must not override RadiologistNotes.\n"
        "- QC and DICOM metadata are technical context only.\n"
        "- Use DICOM metadata only to identify modality, body part, study date, and view when needed.\n"
        "- Do not mix raw QC or DICOM technical metadata into the main radiology report body.\n"
        "- If QC needs to be mentioned, place it in a short separate 'QC note' section.\n"
        "- Do not include the full DICOM StudyInstanceUID in TEMPLATE_TEXT unless the base hospital template explicitly requires it.\n"
        "- The Impression section must summarize the actual abnormal findings from RadiologistNotes.\n"
        "- Never write 'No significant radiological abnormality' when RadiologistNotes contain abnormal findings such as consolidation,\n"
        "  opacity, infiltrate, effusion, pneumothorax, atelectasis, fracture, mass, nodule, or cardiomegaly.\n"
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
    ai_summary = resolved_context.get("AIInterpretationSummary") or {}
    qc_summary = resolved_context.get("QC") or {}
    dicom_summary = resolved_context.get("DICOMSummary") or {}

    dicom_view = dicom_summary.get("ViewPosition")
    dicom_view_text = dicom_view if dicom_view not in (None, "") else "missing"

    context_lines = [
        f"Exam type: {payload.ExamType or ''}",
        f"Output language: {output_language}",
        f"Radiologist notes: {payload.RadiologistNotes or ''}",
        f"Doctor notes: {payload.DoctorNotes or ''}",
        f"AI interpretation summary: {ai_summary.get('summary') or ''}",
        f"AI interpretation status: {ai_summary.get('status') or ''}",
        f"AI critical alert: {ai_summary.get('critical_alert')}",
        f"AI findings count: {ai_summary.get('findings_count') or 0}",
        f"AI warnings: {', '.join(ai_summary.get('warnings') or []) or 'none'}",
        f"QC status: {qc_summary.get('qc_status') or ''}",
        f"QC issue: {qc_summary.get('issue_type') or ''}",
        f"QC recommended action: {qc_summary.get('recommended_action') or ''}",
        f"QC human review required: {qc_summary.get('human_review_required')}",
        f"QC confidence: {qc_summary.get('confidence') if qc_summary.get('confidence') is not None else ''}",
        f"DICOM modality: {dicom_summary.get('Modality') or ''}",
        f"DICOM body part: {dicom_summary.get('BodyPartExamined') or ''}",
        f"DICOM study date: {dicom_summary.get('StudyDate') or ''}",
        f"DICOM view position: {dicom_view_text}",
        f"DICOM study instance UID: {dicom_summary.get('StudyInstanceUID') or ''}",
        f"DICOM accession number: {dicom_summary.get('DICOMAccessionNumber') or resolved_context.get('AccessionNumber') or ''}",
    ]
    compact_context = "\n".join(context_lines)

    return (
        "REPORT FILLING REQUEST:\n\n"
        "BASE_TEMPLATE:\n"
        f"TEMPLATE_NAME: {selected_template.name}\n"
        f"TEMPLATE_TEXT:\n{selected_template.text}\n\n"
        "PATIENT_AND_ORDER_METADATA:\n"
        f"Patient ID: {resolved_context.get('PatientID') or ''}\n"
        f"Patient name: {resolved_context.get('PatientName') or ''}\n"
        f"Order ID: {resolved_context.get('OrderID') or ''}\n"
        f"Order date: {resolved_context.get('OrderDate') or ''}\n"
        f"Date of birth: {resolved_context.get('DateOfBirth') or ''}\n"
        f"National ID: {resolved_context.get('NationalID') or ''}\n"
        f"Gender: {resolved_context.get('Gender') or ''}\n"
        f"Accession number: {resolved_context.get('AccessionNumber') or ''}\n\n"
        "COMPACT_REPORT_CONTEXT:\n"
        f"{compact_context}\n\n"
        "INSTRUCTION:\n"
        "Adapt the BASE_TEMPLATE using only relevant clinical context. Radiologist notes are the\n"
        "primary source for the final report text. Doctor notes are secondary clinical context.\n"
        "AI interpretation summary is secondary and must not override RadiologistNotes. QC and DICOM metadata are technical context only.\n"
        "The Impression section must summarize the actual abnormal findings from RadiologistNotes.\n"
        "Never write 'No significant radiological abnormality' if RadiologistNotes describe abnormal findings.\n"
        "If DoctorNotes and RadiologistNotes conflict, follow RadiologistNotes for imaging finding and location.\n"
        "If QC status is REVIEW_REQUIRED, keep QC in a short separate QC note section rather than mixing it into the main report body.\n"
        "Return one JSON object with the required response keys only. Keep the full template-style\n"
        "report body inside TEMPLATE_TEXT and preserve line breaks. Return valid JSON only without markdown or explanations."
    )
