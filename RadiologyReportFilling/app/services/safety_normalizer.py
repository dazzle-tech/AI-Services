"""Deterministic post-processing for the template-only API response."""
import json
import logging
import re
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Iterable, List

from app.models.schemas import RadiologyReportRequest, RadiologyTemplateResponse
from app.templates.report_templates import ReportTemplate, build_greek_signature_block

logger = logging.getLogger(__name__)

_GREEK_CHEST_TEMPLATE_NAMES = {
    "ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ",
    "ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ 2 ΛΗΨΕΩΝ",
}
_GREEK_CHEST_SECTION_HEADINGS = (
    "Κλινική ένδειξη:",
    "Τεχνική:",
    "Ευρήματα:",
    "Συμπέρασμα:",
)
_GREEK_CHEST_LIMITATION_TECHNIQUE = (
    "Διατίθεται μία ακτινογραφική λήψη θώρακος για αξιολόγηση. "
    "Η αξιολόγηση είναι περιορισμένη λόγω απουσίας πλήρους σειράς λήψεων "
    "και ελλιπών μεταδεδομένων προβολής."
)
_RADIOLOGIST_REVIEW_REQUIRED = "Radiologist review required."
_DICOM_ORDER_MISMATCH_TITLE = "⚠ WARNING: DICOM/ORDER MISMATCH"
_DICOM_ORDER_MISMATCH_SEPARATOR = "─────────────────────────────────────────────────"
_SIGNATURE_LABEL = "Ο ΙΑΤΡΟΣ ΑΚΤΙΝΟΛΟΓΟΣ"


_LEGACY_CONTENT_KEYS = (
    "doctor_notes",
    "radiologist_notes",
    "clinical_report",
    "corrected_doctor_notes",
    "corrected_radiologist_notes",
    "structured_report",
    "findings",
    "warnings",
    "rag_grounding",
    "reconciled_findings",
    "ai_findings_dropped",
    "ai_findings_used_for_enrichment",
    "impression",
    "diagnosis",
    "observations",
    "recommendations",
    "measurements",
)

_LOCALIZED_COPY = {
    "el": {
        "default_title": "ΑΚΤΙΝΟΛΟΓΙΚΗ ΕΚΘΕΣΗ",
        "patient_metadata": "Στοιχεία ασθενούς και παραγγελίας",
        "dicom_summary": "Περίληψη DICOM",
        "patient_id": "Κωδικός Ασθενούς",
        "patient_name": "Ονοματεπώνυμο Ασθενούς",
        "order_id": "Κωδικός Παραγγελίας",
        "order_date": "Ημερομηνία Παραγγελίας",
        "date_of_birth": "Ημερομηνία Γέννησης",
        "national_id": "Αριθμός Ταυτότητας",
        "gender": "Φύλο",
        "accession_number": "Accession Number",
        "modality": "Modality",
        "body_part_examined": "Εξεταζόμενο Μέρος Σώματος",
        "study_date": "Ημερομηνία Μελέτης",
        "dicom_accession_number": "DICOM Accession Number",
        "dicom_patient_id": "DICOM Κωδικός Ασθενούς",
        "dicom_patient_name": "DICOM Ονοματεπώνυμο Ασθενούς",
        "patient_sex": "Φύλο Ασθενούς",
        "manufacturer": "Κατασκευαστής",
        "manufacturer_model_name": "Μοντέλο Κατασκευαστή",
        "indication": "Ένδειξη",
        "technique": "Τεχνική",
        "findings": "Ευρήματα",
        "impression": "Συμπέρασμα",
        "recommendations": "Συστάσεις",
        "clinical_notes": "Σημειώσεις Κλινικού Ιατρού",
        "radiologist_notes": "Σημειώσεις Ακτινολόγου",
        "clinical_report": "Κλινική Έκθεση",
        "diagnosis": "Διάγνωση",
        "observations": "Παρατηρήσεις",
        "measurements": "Μετρήσεις",
        "grounding": "Συσχετισμοί",
        "pending_indication": "Αναμένεται συμπλήρωση της ένδειξης από τον παραπέμποντα ιατρό.",
        "pending_technique": "Αναμένεται συμπλήρωση της τεχνικής από τον ακτινολόγο.",
        "pending_findings": "Αναμένεται συμπλήρωση των ευρημάτων από τον ακτινολόγο.",
        "pending_impression": "Αναμένεται συμπλήρωση του συμπεράσματος από τον ακτινολόγο.",
    },
    "en": {
        "default_title": "RADIOLOGY REPORT",
        "patient_metadata": "Patient and Order Metadata",
        "dicom_summary": "DICOM Summary",
        "patient_id": "Patient ID",
        "patient_name": "Patient Name",
        "order_id": "Order ID",
        "order_date": "Order Date",
        "date_of_birth": "Date of Birth",
        "national_id": "National ID",
        "gender": "Gender",
        "accession_number": "Accession Number",
        "modality": "Modality",
        "body_part_examined": "Body Part Examined",
        "study_date": "Study Date",
        "dicom_accession_number": "DICOM Accession Number",
        "dicom_patient_id": "DICOM Patient ID",
        "dicom_patient_name": "DICOM Patient Name",
        "patient_sex": "Patient Sex",
        "manufacturer": "Manufacturer",
        "manufacturer_model_name": "Manufacturer Model Name",
        "indication": "Indication",
        "technique": "Technique",
        "findings": "Findings",
        "impression": "Impression",
        "recommendations": "Recommendations",
        "clinical_notes": "Clinical Notes",
        "radiologist_notes": "Radiologist Notes",
        "clinical_report": "Clinical Report",
        "diagnosis": "Diagnosis",
        "observations": "Observations",
        "measurements": "Measurements",
        "grounding": "Grounding",
        "pending_indication": "Pending referring clinician details.",
        "pending_technique": "Study details pending radiologist completion.",
        "pending_findings": "Pending radiologist completion.",
        "pending_impression": "Pending radiologist completion.",
    },
    "pt": {
        "default_title": "Relatório de Radiologia",
        "patient_metadata": "Dados do paciente e do pedido",
        "dicom_summary": "Resumo DICOM",
        "patient_id": "ID do Paciente",
        "patient_name": "Nome do Paciente",
        "order_id": "ID do Pedido",
        "order_date": "Data do Pedido",
        "date_of_birth": "Data de Nascimento",
        "national_id": "ID Nacional",
        "gender": "Sexo",
        "accession_number": "Número de Acesso",
        "modality": "Modalidade",
        "body_part_examined": "Parte do Corpo Examinada",
        "study_date": "Data do Estudo",
        "dicom_accession_number": "Número de Acesso DICOM",
        "dicom_patient_id": "ID DICOM do Paciente",
        "dicom_patient_name": "Nome DICOM do Paciente",
        "patient_sex": "Sexo do Paciente",
        "manufacturer": "Fabricante",
        "manufacturer_model_name": "Modelo do Fabricante",
        "indication": "Indicação",
        "technique": "Técnica",
        "findings": "Achados",
        "impression": "Conclusão",
        "recommendations": "Recomendações",
        "clinical_notes": "Notas Clínicas",
        "radiologist_notes": "Notas do Radiologista",
        "clinical_report": "Relatório Clínico",
        "diagnosis": "Diagnóstico",
        "observations": "Observações",
        "measurements": "Medições",
        "grounding": "Referências",
        "pending_indication": "Indicação clínica pendente.",
        "pending_technique": "Detalhes do exame pendentes.",
        "pending_findings": "Achados pendentes de conclusão pelo radiologista.",
        "pending_impression": "Conclusão pendente de conclusão pelo radiologista.",
    },
    "ar": {
        "default_title": "تقرير الأشعة",
        "patient_metadata": "بيانات المريض والطلب",
        "dicom_summary": "ملخص DICOM",
        "patient_id": "معرف المريض",
        "patient_name": "اسم المريض",
        "order_id": "معرف الطلب",
        "order_date": "تاريخ الطلب",
        "date_of_birth": "تاريخ الميلاد",
        "national_id": "الهوية الوطنية",
        "gender": "الجنس",
        "accession_number": "رقم الدخول",
        "modality": "نوع الفحص",
        "body_part_examined": "الجزء المفحوص",
        "study_date": "تاريخ الدراسة",
        "dicom_accession_number": "رقم DICOM للدخول",
        "dicom_patient_id": "معرف DICOM للمريض",
        "dicom_patient_name": "اسم DICOM للمريض",
        "patient_sex": "جنس المريض",
        "manufacturer": "الشركة المصنّعة",
        "manufacturer_model_name": "طراز الشركة المصنّعة",
        "indication": "الاستطباب",
        "technique": "الطريقة",
        "findings": "النتائج",
        "impression": "الانطباع",
        "recommendations": "التوصيات",
        "clinical_notes": "ملاحظات الطبيب السريري",
        "radiologist_notes": "ملاحظات اختصاصي الأشعة",
        "clinical_report": "التقرير السريري",
        "diagnosis": "التشخيص",
        "observations": "الملاحظات",
        "measurements": "القياسات",
        "grounding": "المرجعيات",
        "pending_indication": "بانتظار استكمال الاستطباب من الطبيب المحيل.",
        "pending_technique": "بانتظار استكمال تفاصيل الفحص من اختصاصي الأشعة.",
        "pending_findings": "بانتظار استكمال النتائج من اختصاصي الأشعة.",
        "pending_impression": "بانتظار استكمال الانطباع من اختصاصي الأشعة.",
    },
}


def _unwrap_if_wrapped(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Peel off legacy envelope keys when the model returns the old response shape."""
    if not isinstance(raw, dict):
        return {}
    for key in ("safety_normalized_output", "raw_model_output"):
        inner = raw.get(key)
        if isinstance(inner, dict):
            logger.warning("Model returned legacy response envelope; unwrapping %s.", key)
            return inner
    return raw


def _clean_text(value: Any) -> str:
    """Return a user-safe text representation."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _clean_report_text(value: Any) -> str:
    """Preserve report text formatting while normalizing newlines."""
    text = _clean_text(value)
    if not text:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _resolve_output_language(payload: RadiologyReportRequest) -> str:
    """Read the normalized output language from the request model."""
    language = _clean_text(payload.OutputLanguage).lower()
    return language if language in _LOCALIZED_COPY else "el"


def _localized(output_language: str, key: str) -> str:
    """Look up localized labels used by deterministic fallbacks."""
    return _LOCALIZED_COPY.get(output_language, _LOCALIZED_COPY["el"])[key]


def _resolve_signing_physician_name(
    payload: RadiologyReportRequest,
    raw: Dict[str, Any],
    fallback_physician: str | None = None,
) -> str | None:
    for value in (
        payload.SigningPhysician,
        fallback_physician,
    ):
        text = _clean_text(value)
        if text:
            return text
    return None


def _resolve_signing_physician_code(payload: RadiologyReportRequest) -> str | None:
    text = _clean_text(payload.SigningPhysicianCode)
    return text or None


def _apply_runtime_signature(
    template_text: str,
    payload: RadiologyReportRequest,
    fallback_physician: str | None = None,
) -> str:
    """Ensure Greek reports end with the runtime signature block."""
    if _resolve_output_language(payload) != "el":
        return template_text

    signature_block = build_greek_signature_block(
        _resolve_signing_physician_name(payload, {}, fallback_physician),
        _resolve_signing_physician_code(payload),
    )
    marker = _SIGNATURE_LABEL
    if marker in template_text:
        prefix, _, _ = template_text.rpartition(marker)
        return f"{prefix.rstrip()}\n\n{signature_block}".strip()
    return f"{template_text.rstrip()}\n\n{signature_block}".strip()


def _normalize_token(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean_text(value)).upper()


def _contains_greek(text: str) -> bool:
    return bool(re.search(r"[Α-Ωα-ωΆΈΉΊΌΎΏάέήίόύώϊϋΐΰ]", text))


def _extract_structured_report_text(raw: Dict[str, Any], key: str) -> str:
    structured_report = raw.get("structured_report")
    if isinstance(structured_report, dict):
        return _clean_report_text(structured_report.get(key))
    return ""


def _extract_labeled_section(template_text: str, label: str) -> str:
    lines = template_text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    collected: list[str] = []
    capture = False
    for line in lines:
        stripped = line.strip()
        if stripped == label:
            capture = True
            continue
        if capture and (stripped in _GREEK_CHEST_SECTION_HEADINGS or stripped == _SIGNATURE_LABEL):
            break
        if capture:
            collected.append(line.rstrip())
    return "\n".join(line for line in collected if line.strip()).strip()


def _extract_section_with_headings(template_text: str, label: str, section_breaks: set[str]) -> str:
    lines = template_text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    collected: list[str] = []
    capture = False
    for line in lines:
        stripped = line.strip().rstrip(":")
        if stripped == label.rstrip(":"):
            capture = True
            continue
        if capture and stripped in {section.rstrip(":") for section in section_breaks}:
            break
        if capture:
            collected.append(line.rstrip())
    return "\n".join(line for line in collected if line.strip()).strip()


def _append_unique(lines: list[str], line: str) -> None:
    if line and line not in lines:
        lines.append(line)


def _normalize_ai_finding_text(value: Any) -> str:
    text = _clean_report_text(value)
    if not text:
        return ""
    if _RADIOLOGIST_REVIEW_REQUIRED.lower() in text.lower():
        return text
    if text[-1] not in ".!?":
        text = f"{text}."
    return f"{text} {_RADIOLOGIST_REVIEW_REQUIRED}"


def build_dicom_order_mismatch_warning_text(payload: RadiologyReportRequest) -> str:
    dicom = payload.DICOM
    if not isinstance(dicom, dict) or not dicom.get("dicom_order_mismatch"):
        return ""

    uploaded_accession = _clean_text(
        dicom.get("DICOMAccessionNumber")
        or dicom.get("UploadedDICOMAccessionNumber")
        or dicom.get("uploaded_dicom_accession_number")
        or dicom.get("0008,0050")
        or dicom.get("AccessionNumber")
    ) or "unknown"
    order_accession = _clean_text(payload.AccessionNumber) or "unknown"

    return (
        f"{_DICOM_ORDER_MISMATCH_TITLE}\n"
        f"The uploaded DICOM file ({uploaded_accession}) does not match the accession number in the order form "
        f"({order_accession}). Radiologist notes in this report may refer to a different study. Manual verification "
        "is required before this report can be finalised or signed.\n"
        f"{_DICOM_ORDER_MISMATCH_SEPARATOR}"
    )


def _prepend_report_warning(template_text: str, warning_text: str) -> str:
    warning = _clean_report_text(warning_text)
    if not warning or warning in template_text:
        return template_text
    return f"{warning}\n\n{template_text.lstrip()}".strip()


def _is_greek_chest_xray_template(
    payload: RadiologyReportRequest,
    resolved_context: Dict[str, Any] | None,
    selected_template: ReportTemplate | None,
) -> bool:
    if _resolve_output_language(payload) != "el":
        return False
    if selected_template and selected_template.name in _GREEK_CHEST_TEMPLATE_NAMES:
        return True
    modality = _normalize_token((resolved_context or {}).get("DICOMSummary", {}).get("Modality"))
    body_part = _normalize_token((resolved_context or {}).get("DICOMSummary", {}).get("BodyPartExamined"))
    exam_type = _normalize_token(payload.ExamType)
    return modality in {"XR", "XRY", "CR", "DX"} and (
        "CHEST" in body_part or "ΘΩΡΑΚ" in body_part or "CHEST" in exam_type or "ΘΩΡΑΚ" in exam_type
    )


def _resolve_greek_chest_template_name(payload: RadiologyReportRequest, selected_template: ReportTemplate | None) -> str:
    if selected_template and selected_template.name in _GREEK_CHEST_TEMPLATE_NAMES:
        return selected_template.name
    exam_type = _normalize_token(payload.ExamType)
    if any(marker in exam_type for marker in ("2 VIEWS", "TWO VIEWS", "PA/LATERAL", "PA AND LATERAL", "2 ΛΗΨ")):
        return "ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ 2 ΛΗΨΕΩΝ"
    return "ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ"


def _qc_context(payload: RadiologyReportRequest) -> dict[str, Any]:
    if hasattr(payload.QC, "model_dump"):
        return payload.QC.model_dump(exclude_none=True)
    if isinstance(payload.QC, dict):
        return payload.QC
    if isinstance(payload.QCResult, dict):
        return payload.QCResult
    return {}


def _ai_context(payload: RadiologyReportRequest) -> Any:
    if isinstance(payload.AIInterpretation, dict):
        return payload.AIInterpretation
    if hasattr(payload.AIInterpretationSummary, "model_dump"):
        return payload.AIInterpretationSummary.model_dump(exclude_none=True)
    if isinstance(payload.AIInterpretationSummary, dict):
        return payload.AIInterpretationSummary
    return payload.AIInterpretation


def _needs_limited_chest_technique(payload: RadiologyReportRequest) -> bool:
    qc_result = _qc_context(payload)
    if not isinstance(qc_result, dict):
        return False
    qc_status = _normalize_token(qc_result.get("qc_status"))
    if qc_status == "REVIEW_REQUIRED":
        return True
    details = qc_result.get("details")
    if isinstance(details, dict):
        try:
            return int(details.get("num_images")) == 1
        except (TypeError, ValueError):
            return False
    return False


_CHEST_ABNORMAL_TERMS = (
    "consolidation",
    "opacity",
    "infiltrate",
    "effusion",
    "pneumothorax",
    "atelectasis",
    "fracture",
    "mass",
    "nodule",
    "cardiomegaly",
)


def _resolve_greek_chest_indication(raw: Dict[str, Any], payload: RadiologyReportRequest) -> str:
    for candidate in (
        _extract_structured_report_text(raw, "indication"),
        _extract_labeled_section(_clean_report_text(raw.get("TEMPLATE_TEXT")), "Κλινική ένδειξη:"),
    ):
        if candidate and _contains_greek(candidate):
            return candidate

    doctor_notes = _clean_report_text(payload.DoctorNotes)
    if not doctor_notes:
        return _localized("el", "pending_indication")
    if _contains_greek(doctor_notes):
        return doctor_notes

    notes_lower = doctor_notes.lower()
    complaint_parts: list[str] = []
    if "chest pain" in notes_lower:
        complaint_parts.append("Οξύ θωρακικό άλγος" if "acute chest pain" in notes_lower else "Θωρακικό άλγος")
    if "persistent cough" in notes_lower:
        complaint_parts.append("επίμονος βήχας")
    elif "cough" in notes_lower:
        complaint_parts.append("βήχας")

    sentences: list[str] = []
    if complaint_parts:
        sentences.append(" και ".join(complaint_parts) + ".")
    if "pneumonia" in notes_lower:
        sentences.append("Κλινική υποψία πνευμονίας.")
    if sentences:
        return " ".join(sentences)
    return doctor_notes


def _resolve_greek_chest_technique(
    raw: Dict[str, Any],
    payload: RadiologyReportRequest,
    template_name: str,
) -> str:
    if _needs_limited_chest_technique(payload):
        return _GREEK_CHEST_LIMITATION_TECHNIQUE

    for candidate in (
        _extract_structured_report_text(raw, "technique"),
        _extract_labeled_section(_clean_report_text(raw.get("TEMPLATE_TEXT")), "Τεχνική:"),
    ):
        if (
            candidate
            and _contains_greek(candidate)
            and "πρότυπο πρωτόκολλο του τμήματος" not in candidate
        ):
            return candidate

    if template_name == "ΑΚΤΙΝΟΓΡΑΦΙΑ ΘΩΡΑΚΟΣ 2 ΛΗΨΕΩΝ":
        return "Ακτινογραφία θώρακος σε δύο λήψεις."
    return "Ακτινογραφία θώρακος."


def _collect_ai_interpretation_tokens(ai_interpretation: Any) -> list[str]:
    tokens: list[str] = []
    if isinstance(ai_interpretation, dict):
        for key in ("summary", "explanation"):
            value = _clean_report_text(ai_interpretation.get(key))
            if value:
                tokens.append(value)
        findings = ai_interpretation.get("findings")
        if isinstance(findings, list):
            for item in findings:
                if isinstance(item, dict):
                    for key in ("finding_code", "finding_text", "label", "location"):
                        value = _clean_report_text(item.get(key))
                        if value:
                            tokens.append(value)
                else:
                    value = _clean_report_text(item)
                    if value:
                        tokens.append(value)
    else:
        value = _clean_report_text(ai_interpretation)
        if value:
            tokens.append(value)
    return tokens


def _extract_ai_finding_texts(payload: RadiologyReportRequest) -> list[str]:
    """Return normalized AI finding_text values for deterministic report insertion."""
    ai_interpretation = payload.AIInterpretation
    if not isinstance(ai_interpretation, dict):
        return []

    findings = ai_interpretation.get("findings")
    if not isinstance(findings, list):
        return []

    lines: list[str] = []
    for item in findings:
        if isinstance(item, dict):
            text = _normalize_ai_finding_text(
                item.get("finding_text") or item.get("label") or item.get("finding_code")
            )
        else:
            text = _normalize_ai_finding_text(item)
        if text and text not in lines:
            lines.append(text)
    return lines


def _append_ai_findings_to_template_text(
    template_text: str,
    payload: RadiologyReportRequest,
    output_language: str,
) -> str:
    """Merge AIInterpretation.findings into the report Findings section when needed."""
    ai_finding_texts = _extract_ai_finding_texts(payload)
    if not ai_finding_texts:
        return template_text
    if all(text in template_text for text in ai_finding_texts):
        return template_text

    lines = template_text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    findings_heading = _localized(output_language, "findings")
    section_breaks = {
        _localized(output_language, "impression"),
        _localized(output_language, "recommendations"),
        _SIGNATURE_LABEL,
    }
    missing_texts = [text for text in ai_finding_texts if text not in template_text]
    if not missing_texts:
        return template_text

    def _normalized_heading(line: str) -> str:
        return line.strip().rstrip(":")

    findings_index = next(
        (i for i, line in enumerate(lines) if _normalized_heading(line) == findings_heading),
        None,
    )

    if findings_index is not None:
        insert_at = len(lines)
        for idx in range(findings_index + 1, len(lines)):
            if _normalized_heading(lines[idx]) in section_breaks:
                insert_at = idx
                break

        while insert_at > findings_index + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1

        block_lines = [*missing_texts]
        if insert_at < len(lines) and lines[insert_at].strip():
            block_lines.append("")
        lines[insert_at:insert_at] = block_lines
        return "\n".join(lines).strip()

    if _SIGNATURE_LABEL in lines:
        signature_index = next(i for i, line in enumerate(lines) if line.strip() == _SIGNATURE_LABEL)
        block_lines = ["", f"{findings_heading}:", *missing_texts, ""]
        lines[signature_index:signature_index] = block_lines
        return "\n".join(lines).strip()

    return f"{template_text.rstrip()}\n\n{findings_heading}:\n" + "\n".join(missing_texts)


def _resolve_greek_chest_ai_findings(payload: RadiologyReportRequest) -> list[str]:
    ai_tokens = _collect_ai_interpretation_tokens(_ai_context(payload))
    if not ai_tokens:
        return []

    findings: list[str] = []
    combined = " || ".join(ai_tokens).lower()
    has_surgical_clips = "surgical_clips" in combined or ("surgical" in combined and "clip" in combined)
    has_upper_abdomen = "upper abdomen" in combined or "abdomen" in combined or "κοιλια" in combined
    if has_surgical_clips and has_upper_abdomen:
        findings.append("Απεικονίζονται χειρουργικά clips στην άνω κοιλιακή χώρα.")

    has_deg_changes = "degenerative_changes" in combined or "degenerative" in combined or "εκφυλισ" in combined
    has_thoracic_spine = "thoracic spine" in combined or "t-spine" in combined or "spine_thoracic" in combined or "θωρακικ" in combined
    if has_deg_changes and has_thoracic_spine:
        findings.append("Ήπιες εκφυλιστικές αλλοιώσεις της θωρακικής μοίρας της σπονδυλικής στήλης.")

    return findings


def _resolve_greek_chest_findings_and_conclusion(
    raw: Dict[str, Any],
    payload: RadiologyReportRequest,
) -> tuple[list[str], list[str]]:
    findings: list[str] = []
    conclusion: list[str] = []

    radiologist_notes = _clean_report_text(payload.RadiologistNotes)
    notes_lower = radiologist_notes.lower()
    has_right_lower_lobe_opacity = (
        any(term in notes_lower for term in ("right lower lobe", "rll"))
        and any(term in notes_lower for term in ("consolidation", "opacity"))
    )
    has_negative_pneumothorax = any(
        phrase in notes_lower
        for phrase in ("no evidence of pneumothorax", "no pneumothorax", "without pneumothorax", "negative for pneumothorax")
    )

    if has_right_lower_lobe_opacity:
        findings.append(
            "Παρατηρείται πύκνωση-σκίαση στην προβολή του δεξιού κάτω λοβού, σύμφωνα με τις διαθέσιμες σημειώσεις."
        )
        conclusion.append(
            "Πύκνωση-σκίαση δεξιού κάτω λοβού, πιθανώς φλεγμονώδους αιτιολογίας στο κατάλληλο κλινικό πλαίσιο."
        )
    if has_negative_pneumothorax:
        findings.append("Δεν αναγνωρίζεται εμφανής πνευμοθώρακας.")
        conclusion.append("Δεν αναγνωρίζεται εμφανής πνευμοθώρακας.")

    for ai_line in _resolve_greek_chest_ai_findings(payload):
        _append_unique(findings, ai_line)

    if not findings:
        fallback_lines = _extract_structured_report_text(raw, "findings") or _extract_labeled_section(
            _clean_report_text(raw.get("TEMPLATE_TEXT")),
            "Ευρήματα:",
        )
        if fallback_lines:
            findings.extend(line.strip() for line in fallback_lines.splitlines() if line.strip())
        else:
            findings.append(_localized("el", "pending_findings"))

    if _needs_limited_chest_technique(payload):
        conclusion.insert(0, "Περιορισμένη αξιολόγηση λόγω μίας διαθέσιμης λήψης.")

    if not conclusion:
        fallback_conclusion = _extract_structured_report_text(raw, "impression") or _extract_labeled_section(
            _clean_report_text(raw.get("TEMPLATE_TEXT")),
            "Συμπέρασμα:",
        )
        if fallback_conclusion:
            conclusion.extend(line.strip() for line in fallback_conclusion.splitlines() if line.strip())
        else:
            conclusion.append(_localized("el", "pending_impression"))

    return findings, conclusion


def _build_greek_chest_signature(
    payload: RadiologyReportRequest,
    selected_template: ReportTemplate | None,
    raw: Dict[str, Any],
) -> str:
    fallback_physician = selected_template.physician if selected_template is not None else None
    return build_greek_signature_block(
        _resolve_signing_physician_name(payload, raw, fallback_physician),
        _resolve_signing_physician_code(payload),
    )


def _build_greek_chest_template_text(
    raw: Dict[str, Any],
    payload: RadiologyReportRequest,
    selected_template: ReportTemplate | None,
) -> str:
    template_name = _resolve_greek_chest_template_name(payload, selected_template)
    indication = _resolve_greek_chest_indication(raw, payload)
    technique = _resolve_greek_chest_technique(raw, payload, template_name)
    findings, conclusion = _resolve_greek_chest_findings_and_conclusion(raw, payload)
    signature = _build_greek_chest_signature(payload, selected_template, raw)
    findings_block = "\n".join(findings).strip()
    conclusion_block = "\n".join(conclusion).strip()
    return (
        f"{template_name}\n\n"
        "Κλινική ένδειξη:\n"
        f"{indication}\n\n"
        "Τεχνική:\n"
        f"{technique}\n\n"
        "Ευρήματα:\n"
        f"{findings_block}\n\n"
        "Συμπέρασμα:\n"
        f"{conclusion_block}\n\n"
        f"{signature}"
    ).strip()


def _is_chest_xray_context(
    payload: RadiologyReportRequest,
    resolved_context: Dict[str, Any] | None,
    selected_template: ReportTemplate | None,
) -> bool:
    modality = _normalize_token((resolved_context or {}).get("DICOMSummary", {}).get("Modality"))
    body_part = _normalize_token((resolved_context or {}).get("DICOMSummary", {}).get("BodyPartExamined"))
    exam_type = _normalize_token(payload.ExamType)
    if selected_template and "CHEST" in _normalize_token(selected_template.name):
        return True
    return modality in {"XR", "XRY", "CR", "DX"} and "CHEST" in (body_part or exam_type)


def _has_abnormal_radiologist_notes(notes: str) -> bool:
    lowered = notes.lower()
    return any(term in lowered for term in _CHEST_ABNORMAL_TERMS)


def _split_report_sentences(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    pieces = re.split(r"(?<=[.!?])\s+|\n+", normalized)
    return [piece.strip() for piece in pieces if piece.strip()]


def _strip_chest_note_prefix(text: str) -> str:
    return re.sub(
        r"^(?:pa\s*/\s*lateral\s*chest|pa\s+and\s+lateral\s+chest|pa\s*/\s*lateral|pa\s+and\s+lateral|chest)\s*:?\s*",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )


def _resolve_english_chest_indication(raw: Dict[str, Any], payload: RadiologyReportRequest) -> str:
    for candidate in (
        _extract_structured_report_text(raw, "indication"),
        _extract_section_with_headings(
            _clean_report_text(raw.get("TEMPLATE_TEXT")),
            "Clinical indication:",
            {"Technique", "Findings", "Impression", "QC note"},
        ),
    ):
        if candidate:
            return candidate

    doctor_notes = _clean_report_text(payload.DoctorNotes)
    if not doctor_notes:
        return "Pending referring clinician details."

    notes_lower = doctor_notes.lower()
    complaint_parts: list[str] = []
    if "chest pain" in notes_lower:
        complaint_parts.append("Acute chest pain" if "acute chest pain" in notes_lower else "Chest pain")
    if "persistent cough" in notes_lower:
        complaint_parts.append("persistent cough")
    elif "cough" in notes_lower:
        complaint_parts.append("cough")

    sentences: list[str] = []
    if complaint_parts:
        sentences.append(" and ".join(complaint_parts) + ".")
    if "pneumonia" in notes_lower:
        sentences.append("Clinical suspicion of pneumonia.")
    if sentences:
        return " ".join(sentences)
    return doctor_notes


def _resolve_english_chest_technique(payload: RadiologyReportRequest) -> str:
    exam_type = _normalize_token(payload.ExamType)
    radiologist_notes = _normalize_token(payload.RadiologistNotes)
    if (
        "PA/LATERAL" in exam_type
        or "PA AND LATERAL" in exam_type
        or "2 VIEWS" in exam_type
        or "PA/LATERAL" in radiologist_notes
        or "PA AND LATERAL" in radiologist_notes
    ):
        return "PA and lateral chest radiographs were obtained."
    return "Chest radiographs were obtained."


def _resolve_english_qc_note(payload: RadiologyReportRequest, resolved_context: Dict[str, Any] | None) -> str | None:
    qc_result = _qc_context(payload)
    if not isinstance(qc_result, dict):
        return None
    if _normalize_token(qc_result.get("qc_status")) != "REVIEW_REQUIRED":
        return None

    dicom_summary = (resolved_context or {}).get("DICOMSummary") or {}
    view_position = _clean_text(dicom_summary.get("ViewPosition"))
    recommended_action = _clean_text(qc_result.get("recommended_action"))
    issue_type = _normalize_token(qc_result.get("issue_type"))
    if not view_position and (
        issue_type == "MISSING_METADATA" or "VIEWPOSITION" in recommended_action.upper()
    ):
        return "DICOM ViewPosition metadata is missing. Human review is required."
    if recommended_action:
        action = recommended_action.rstrip(".")
        return f"{action}. Human review is required."
    return "Human review is required."


def _resolve_english_chest_findings_and_impression(payload: RadiologyReportRequest) -> tuple[list[str], list[str]]:
    radiologist_notes = _clean_report_text(payload.RadiologistNotes)
    notes_lower = radiologist_notes.lower()
    findings: list[str] = []
    impression: list[str] = []

    has_right_lower_lobe_opacity = (
        any(term in notes_lower for term in ("right lower lobe", "rll"))
        and any(term in notes_lower for term in ("consolidation", "opacity"))
    )
    has_negative_pneumothorax = any(
        phrase in notes_lower
        for phrase in ("no evidence of pneumothorax", "no pneumothorax", "without pneumothorax", "negative for pneumothorax")
    )

    if has_right_lower_lobe_opacity:
        findings.append("Consolidation/opacity is noted in the right lower lobe.")
        impression.append("Right lower lobe consolidation/opacity, suspicious for pneumonia in the appropriate clinical context.")

    sentences = [_strip_chest_note_prefix(sentence) for sentence in _split_report_sentences(radiologist_notes)]
    for sentence in sentences:
        if not sentence:
            continue
        sentence_lower = sentence.lower()
        if has_right_lower_lobe_opacity and "right lower lobe" in sentence_lower and (
            "consolidation" in sentence_lower or "opacity" in sentence_lower
        ):
            continue
        if any(term in sentence_lower for term in _CHEST_ABNORMAL_TERMS):
            normalized = sentence if sentence.endswith((".", "!", "?")) else f"{sentence}."
            if normalized not in findings:
                findings.append(normalized)

    if has_negative_pneumothorax:
        if "No evidence of pneumothorax." not in findings:
            findings.append("No evidence of pneumothorax.")
        impression.append("No pneumothorax.")

    if not findings:
        cleaned = _strip_chest_note_prefix(radiologist_notes)
        if cleaned:
            findings.append(cleaned if cleaned.endswith((".", "!", "?")) else f"{cleaned}.")
        else:
            findings.append("Pending radiologist completion.")

    if not impression:
        positive_findings = [line for line in findings if "pneumothorax" not in line.lower() or "no evidence" not in line.lower()]
        if positive_findings and _has_abnormal_radiologist_notes(radiologist_notes):
            impression.append(positive_findings[0])
        else:
            impression.append("Pending radiologist completion.")
        if has_negative_pneumothorax and "No pneumothorax." not in impression:
            impression.append("No pneumothorax.")

    return findings, impression


def _build_english_chest_template_text(
    raw: Dict[str, Any],
    payload: RadiologyReportRequest,
    resolved_context: Dict[str, Any] | None,
    selected_template: ReportTemplate | None,
) -> str:
    template_name = _clean_report_text(raw.get("TEMPLATE_NAME")) or (
        selected_template.name if selected_template is not None else "RADIOLOGY REPORT"
    )
    indication = _resolve_english_chest_indication(raw, payload)
    technique = _resolve_english_chest_technique(payload)
    findings, impression = _resolve_english_chest_findings_and_impression(payload)
    qc_note = _resolve_english_qc_note(payload, resolved_context)

    sections = [
        template_name,
        "",
        "Clinical indication:",
        indication,
        "",
        "Technique:",
        technique,
        "",
        "Findings:",
        "\n".join(findings).strip(),
        "",
        "Impression:",
        "\n".join(impression).strip(),
    ]
    if qc_note:
        sections.extend(["", "QC note:", qc_note])
    return "\n".join(section for section in sections if section is not None).strip()


def _should_rebuild_english_chest_template(
    payload: RadiologyReportRequest,
    template_text: str,
    resolved_context: Dict[str, Any] | None,
    selected_template: ReportTemplate | None,
) -> bool:
    if _resolve_output_language(payload) != "en":
        return False
    if not _is_chest_xray_context(payload, resolved_context, selected_template):
        return False
    radiologist_notes = _clean_report_text(payload.RadiologistNotes)
    if not radiologist_notes:
        return False

    lowered_template = template_text.lower()
    if "studyinstanceuid" in lowered_template or "study instance uid" in lowered_template:
        return True
    if _resolve_english_qc_note(payload, resolved_context) and "qc note:" not in lowered_template:
        return True
    if _has_abnormal_radiologist_notes(radiologist_notes):
        if "no significant radiological abnormality" in lowered_template:
            return True
        notes_lower = radiologist_notes.lower()
        if "right lower lobe" in notes_lower and "right lower lobe" not in lowered_template:
            return True
        if "consolidation" in notes_lower and "consolidation" not in lowered_template:
            return True
        if "opacity" in notes_lower and "opacity" not in lowered_template:
            return True
        if "no evidence of pneumothorax" in notes_lower and "no evidence of pneumothorax" not in lowered_template:
            return True
        if "impression:" not in lowered_template:
            return True
    return False


def _format_metadata_line(label: str, value: Any) -> str:
    text = _clean_text(value)
    return f"{label}: {text}" if text else ""


def _format_findings(findings: Iterable[Any]) -> List[str]:
    lines: List[str] = []
    for item in findings:
        if isinstance(item, dict):
            label = _clean_text(item.get("label")) or "Finding"
            parts = [label]
            location = _clean_text(item.get("location"))
            status = _clean_text(item.get("status"))
            size_cm = item.get("size_cm")
            if location:
                parts.append(f"location: {location}")
            if status:
                parts.append(f"status: {status}")
            if size_cm not in (None, ""):
                parts.append(f"size_cm: {size_cm}")
            lines.append("- " + "; ".join(parts))
        else:
            text = _clean_text(item)
            if text:
                lines.append(f"- {text}")
    return lines


def _format_mapping(title: str, mapping: Dict[str, Any]) -> List[str]:
    lines = [title]
    for key, value in mapping.items():
        text = _clean_text(value)
        if text:
            lines.append(f"{key}: {text}")
    return lines


def _format_legacy_content(raw: Dict[str, Any], output_language: str) -> List[str]:
    sections: List[str] = []

    note_mappings = (
        (_localized(output_language, "clinical_notes"), raw.get("doctor_notes") or raw.get("corrected_doctor_notes")),
        (_localized(output_language, "radiologist_notes"), raw.get("radiologist_notes") or raw.get("corrected_radiologist_notes")),
        (_localized(output_language, "clinical_report"), raw.get("clinical_report")),
        (_localized(output_language, "diagnosis"), raw.get("diagnosis")),
        (_localized(output_language, "observations"), raw.get("observations")),
        (_localized(output_language, "recommendations"), raw.get("recommendations")),
    )
    for title, value in note_mappings:
        text = _clean_report_text(value)
        if text:
            sections.extend([title, text, ""])

    structured_report = raw.get("structured_report")
    if isinstance(structured_report, dict):
        indication = _clean_report_text(structured_report.get("indication"))
        technique = _clean_report_text(structured_report.get("technique"))
        impression = _clean_report_text(structured_report.get("impression"))
        if indication:
            sections.extend([_localized(output_language, "indication"), indication, ""])
        if technique:
            sections.extend([_localized(output_language, "technique"), technique, ""])
        findings = structured_report.get("findings")
        if isinstance(findings, list) and findings:
            sections.append(_localized(output_language, "findings"))
            sections.extend(_format_findings(findings))
            sections.append("")
        if impression:
            sections.extend([_localized(output_language, "impression"), impression, ""])

    findings = raw.get("findings")
    if isinstance(findings, list) and findings:
        sections.append(_localized(output_language, "findings"))
        sections.extend(_format_findings(findings))
        sections.append("")

    warnings = raw.get("warnings")
    if isinstance(warnings, list) and warnings:
        sections.append(_localized(output_language, "recommendations"))
        sections.extend(_format_findings(warnings))
        sections.append("")

    measurements = raw.get("measurements")
    if measurements:
        text = _clean_report_text(measurements)
        if text:
            sections.extend([_localized(output_language, "measurements"), text, ""])

    rag_grounding = raw.get("rag_grounding")
    if isinstance(rag_grounding, dict) and rag_grounding:
        sections.extend(_format_mapping(_localized(output_language, "grounding"), rag_grounding))
        sections.append("")

    for key in ("reconciled_findings", "ai_findings_dropped", "ai_findings_used_for_enrichment"):
        value = raw.get(key)
        if isinstance(value, list) and value:
            sections.append(key.replace("_", " ").title())
            sections.extend(_format_findings(value))
            sections.append("")

    return [line for line in sections if line is not None]


def _join_report_sections(sections: List[str]) -> str:
    """Join report sections while preserving deliberate blank lines."""
    return "\n".join(line for line in sections if line != "").strip()


def _build_legacy_only_template_text(raw: Dict[str, Any], output_language: str) -> str:
    """Turn legacy structured fragments into a single report body."""
    sections = []
    template_name = _clean_report_text(raw.get("TEMPLATE_NAME")) or _localized(output_language, "default_title")
    sections.extend([template_name, ""])
    legacy_sections = _format_legacy_content(raw, output_language)
    if legacy_sections:
        sections.extend(legacy_sections)
    else:
        sections.extend(
            [
                _localized(output_language, "findings"),
                _localized(output_language, "pending_findings"),
                "",
                _localized(output_language, "impression"),
                _localized(output_language, "pending_impression"),
            ]
        )
    return _join_report_sections(sections)


def _build_fallback_template_text(payload: RadiologyReportRequest, raw: Dict[str, Any], output_language: str) -> str:
    metadata_lines = [
        _format_metadata_line(_localized(output_language, "patient_id"), payload.PatientID),
        _format_metadata_line(_localized(output_language, "patient_name"), payload.PatientName),
        _format_metadata_line(_localized(output_language, "order_id"), payload.OrderID),
        _format_metadata_line(_localized(output_language, "order_date"), payload.OrderDate.isoformat() if payload.OrderDate else None),
        _format_metadata_line(_localized(output_language, "date_of_birth"), payload.DateOfBirth.isoformat() if payload.DateOfBirth else None),
        _format_metadata_line(_localized(output_language, "national_id"), payload.NationalID),
        _format_metadata_line(_localized(output_language, "gender"), payload.Gender),
        _format_metadata_line(_localized(output_language, "accession_number"), payload.AccessionNumber),
    ]
    sections = [
        _localized(output_language, "default_title"),
        "",
        _localized(output_language, "patient_metadata"),
        *[line for line in metadata_lines if line],
        "",
        _localized(output_language, "indication"),
        _localized(output_language, "pending_indication"),
        "",
        _localized(output_language, "technique"),
        _localized(output_language, "pending_technique"),
        "",
    ]

    legacy_sections = _format_legacy_content(raw, output_language)
    if legacy_sections:
        sections.extend(legacy_sections)
    else:
        sections.extend(
            [
                _localized(output_language, "findings"),
                _localized(output_language, "pending_findings"),
                "",
                _localized(output_language, "impression"),
                _localized(output_language, "pending_impression"),
            ]
        )

    return _join_report_sections(sections)


def _build_resolved_template_text(
    resolved_context: Dict[str, Any],
    raw: Dict[str, Any],
    output_language: str,
) -> str:
    metadata_lines = [
        _format_metadata_line(_localized(output_language, "patient_id"), resolved_context.get("PatientID")),
        _format_metadata_line(_localized(output_language, "patient_name"), resolved_context.get("PatientName")),
        _format_metadata_line(_localized(output_language, "order_id"), resolved_context.get("OrderID")),
        _format_metadata_line(
            _localized(output_language, "order_date"),
            resolved_context["OrderDate"].isoformat() if isinstance(resolved_context.get("OrderDate"), datetime) else None,
        ),
        _format_metadata_line(
            _localized(output_language, "date_of_birth"),
            resolved_context["DateOfBirth"].isoformat()
            if isinstance(resolved_context.get("DateOfBirth"), datetime)
            else None,
        ),
        _format_metadata_line(_localized(output_language, "national_id"), resolved_context.get("NationalID")),
        _format_metadata_line(_localized(output_language, "gender"), resolved_context.get("Gender")),
        _format_metadata_line(_localized(output_language, "accession_number"), resolved_context.get("AccessionNumber")),
    ]
    dicom_summary = resolved_context.get("DICOMSummary") or {}
    dicom_lines = [
        _format_metadata_line(_localized(output_language, "modality"), dicom_summary.get("Modality")),
        _format_metadata_line(_localized(output_language, "body_part_examined"), dicom_summary.get("BodyPartExamined")),
        _format_metadata_line(_localized(output_language, "study_date"), dicom_summary.get("StudyDate")),
        _format_metadata_line(_localized(output_language, "dicom_accession_number"), dicom_summary.get("AccessionNumber")),
        _format_metadata_line(_localized(output_language, "dicom_patient_id"), dicom_summary.get("PatientID")),
        _format_metadata_line(_localized(output_language, "dicom_patient_name"), dicom_summary.get("PatientName")),
        _format_metadata_line(_localized(output_language, "patient_sex"), dicom_summary.get("PatientSex")),
        _format_metadata_line(_localized(output_language, "manufacturer"), dicom_summary.get("Manufacturer")),
        _format_metadata_line(_localized(output_language, "manufacturer_model_name"), dicom_summary.get("ManufacturerModelName")),
    ]
    sections = [
        _localized(output_language, "default_title"),
        "",
        _localized(output_language, "patient_metadata"),
        *[line for line in metadata_lines if line],
        "",
    ]
    if any(dicom_lines):
        sections.extend([_localized(output_language, "dicom_summary"), *[line for line in dicom_lines if line], ""])
    sections.extend(
        [
            _localized(output_language, "indication"),
            _localized(output_language, "pending_indication"),
            "",
            _localized(output_language, "technique"),
            _localized(output_language, "pending_technique"),
            "",
        ]
    )

    legacy_sections = _format_legacy_content(raw, output_language)
    if legacy_sections:
        sections.extend(legacy_sections)
    else:
        sections.extend(
            [
                _localized(output_language, "findings"),
                _localized(output_language, "pending_findings"),
                "",
                _localized(output_language, "impression"),
                _localized(output_language, "pending_impression"),
                "",
                _localized(output_language, "recommendations"),
                _localized(output_language, "pending_impression"),
            ]
        )

    return _join_report_sections(sections)


def _resolve_template_text(
    raw: Dict[str, Any],
    payload: RadiologyReportRequest,
    resolved_context: Dict[str, Any] | None = None,
) -> str:
    output_language = _resolve_output_language(payload)
    template_text = _clean_report_text(raw.get("TEMPLATE_TEXT"))
    legacy_sections_present = any(raw.get(key) for key in _LEGACY_CONTENT_KEYS)
    legacy_text = _build_legacy_only_template_text(raw, output_language) if legacy_sections_present else ""
    if template_text and not legacy_sections_present:
        return template_text
    if template_text and legacy_sections_present:
        merged = [template_text, "", legacy_text]
        return "\n".join(part for part in merged if part).strip()
    if legacy_text:
        return legacy_text
    return (
        _build_resolved_template_text(resolved_context, raw, output_language)
        if resolved_context
        else _build_fallback_template_text(payload, raw, output_language)
    )


def _extract_title_from_text(template_text: str) -> str:
    """Use the first non-empty line of the report as a fallback template name."""
    for line in template_text.splitlines():
        candidate = line.strip()
        if candidate:
            return candidate
    return ""


def _resolve_template_name(
    raw: Dict[str, Any],
    template_text: str,
    payload: RadiologyReportRequest,
) -> str:
    """Resolve TEMPLATE_NAME without exposing extra request fields."""
    raw_name = _clean_report_text(raw.get("TEMPLATE_NAME"))
    if raw_name:
        return raw_name
    title_from_text = _extract_title_from_text(template_text)
    if title_from_text:
        return title_from_text
    return _localized(_resolve_output_language(payload), "default_title")


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def normalize_report_template(
    raw: Dict[str, Any],
    payload: RadiologyReportRequest,
    resolved_context: Dict[str, Any] | None = None,
    selected_template: ReportTemplate | None = None,
) -> RadiologyTemplateResponse:
    """Normalize model output into the template-only API response."""
    raw = _unwrap_if_wrapped(deepcopy(raw))
    output_language = _resolve_output_language(payload)
    is_greek_chest_xray = _is_greek_chest_xray_template(payload, resolved_context, selected_template)
    if is_greek_chest_xray:
        template_text = _build_greek_chest_template_text(raw, payload, selected_template)
    else:
        template_text = _resolve_template_text(raw, payload, resolved_context)
        if _should_rebuild_english_chest_template(payload, template_text, resolved_context, selected_template):
            template_text = _build_english_chest_template_text(raw, payload, resolved_context, selected_template)
    if not template_text and selected_template is not None:
        template_text = selected_template.text
    if not is_greek_chest_xray:
        template_text = _append_ai_findings_to_template_text(
            template_text,
            payload,
            output_language,
        )
    template_text = _prepend_report_warning(template_text, build_dicom_order_mismatch_warning_text(payload))
    template_text = _apply_runtime_signature(
        template_text,
        payload,
        selected_template.physician if selected_template is not None else None,
    )
    template_name = _resolve_template_name(raw, template_text, payload)
    if template_name == _localized(output_language, "default_title") and selected_template is not None:
        template_name = selected_template.name
    physician = _resolve_signing_physician_name(
        payload,
        raw,
        selected_template.physician if selected_template is not None else None,
    )

    return RadiologyTemplateResponse(
        ID=_coerce_int(raw.get("ID"), default=0),
        TEMPLATE_NAME=template_name,
        TEMPLATE_TEXT=template_text,
        STATUS_ID=_coerce_optional_int(raw.get("STATUS_ID")),
        CREATED_BY=_clean_text(raw.get("CREATED_BY")) or None,
        CREATION_DATETIME=_coerce_optional_datetime(raw.get("CREATION_DATETIME")),
        DELETED_BY=_clean_text(raw.get("DELETED_BY")) or None,
        DELETE_DATETIME=_coerce_optional_datetime(raw.get("DELETE_DATETIME")),
        UPDATED_BY=_clean_text(raw.get("UPDATED_BY")) or None,
        UPDATE_DATETIME=_coerce_optional_datetime(raw.get("UPDATE_DATETIME")),
        Physician=physician,
    )
