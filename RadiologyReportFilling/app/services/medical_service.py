"""Service layer orchestrating the radiology report filling pipeline."""
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict

from app.ai.client import MedicalAIClient
from app.ai.prompts import build_report_filling_system_prompt, build_report_filling_user_prompt
from app.core.config import settings
from app.models.schemas import (
    AnalysisMatchingRequest,
    AnalysisMatchingResponse,
    AnalysisMatchingSafetyOutput,
    Icd10Suggestion,
    RadiologyReportRequest,
    RadiologyTemplateResponse,
    ReconciledFinding,
    ReportCorrectionRequest,
    ReportCorrectionResponse,
    ReportCorrectionSafetyOutput,
    WorkflowWarning,
)
from app.services.rag_store import RagStore
from app.services.safety_normalizer import (
    build_dicom_order_mismatch_warning_text,
    normalize_report_template,
)
from app.templates.report_templates import (
    ReportTemplate,
    build_greek_signature_block,
    select_report_template,
)

logger = logging.getLogger(__name__)

_LATERALITY_PATTERNS = {
    "left": re.compile(r"\bleft(?:-sided)?\b", re.IGNORECASE),
    "right": re.compile(r"\bright(?:-sided)?\b", re.IGNORECASE),
    "bilateral": re.compile(r"\bbilateral\b", re.IGNORECASE),
}

_NEGATION_PREFIXES = ("no", "without", "absent", "negative for")
_STOPWORDS = {
    "the",
    "and",
    "with",
    "from",
    "that",
    "this",
    "not",
    "noted",
    "there",
    "evidence",
    "review",
    "required",
    "image",
    "study",
    "views",
    "view",
    "acute",
    "chest",
    "xray",
    "x",
    "ray",
    "lateral",
    "single",
}

_MODEL_FAILURE_NOTES = {
    "el": "Σημείωση: Η αυτόματη παραγωγή της έκθεσης από AI απέτυχε ή επέστρεψε μη έγκυρο JSON. Απαιτείται έλεγχος από ακτινολόγο.",
    "en": "Note: Automatic AI report generation failed or returned invalid JSON. Radiologist review is required.",
    "pt": "Nota: A geração automática do relatório por IA falhou ou devolveu JSON inválido. É necessária revisão por radiologista.",
    "ar": "ملاحظة: فشل الإنشاء التلقائي للتقرير بالذكاء الاصطناعي أو أعاد JSON غير صالح. يلزم مراجعة اختصاصي الأشعة.",
}

_SIGNATURE_TITLES = {
    "el": "Ο ΙΑΤΡΟΣ ΑΚΤΙΝΟΛΟΓΟΣ",
    "en": "RADIOLOGIST",
    "pt": "RADIOLOGISTA",
    "ar": "اختصاصي الأشعة",
}

_GENERIC_TEMPLATE_NAMES = {
    "el": "ΑΚΤΙΝΟΛΟΓΙΚΗ ΕΚΘΕΣΗ",
    "en": "RADIOLOGY REPORT",
    "pt": "Relatório de Radiologia",
    "ar": "تقرير الأشعة",
}


def _project_path(relative: str) -> str:
    """Resolve a path relative to the project root."""
    return os.path.join(settings.project_dir, relative)


def get_dicom_value(dicom: dict | None, tag: str, default=None):
    """Extract a raw Value from a flexible DICOM tag dictionary."""
    if not dicom:
        return default
    item = dicom.get(tag)
    if not isinstance(item, dict):
        return default
    return item.get("Value", default)


def get_dicom_field(dicom: dict | None, tag: str, flat_name: str, default=None):
    """Read a DICOM value from tag objects or flat workflow keys."""
    value = get_dicom_value(dicom, tag, default=None)
    if value not in (None, ""):
        return value
    if not dicom:
        return default
    flat_value = dicom.get(flat_name)
    if flat_value not in (None, ""):
        return flat_value
    return default


def parse_dicom_date(value):
    """Convert a DICOM YYYYMMDD string into an ISO-like datetime string."""
    if not value:
        return None
    if isinstance(value, str) and len(value) == 8 and value.isdigit():
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]}T00:00:00"
    return value


def _coerce_iso_datetime(value: Any) -> datetime | None:
    """Coerce ISO-like input into a datetime object."""
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


def _coerce_string(value: Any) -> str | None:
    """Normalize loose values to trimmed strings."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value)


def _select_first_non_empty(*values: Any) -> Any:
    """Return the first non-empty candidate value."""
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _resolve_output_language(value: Any) -> str:
    """Normalize the requested output language for internal use."""
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return "el"


def _coerce_bool(value: Any) -> bool | None:
    """Normalize loose booleans used in workflow payloads."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
    return None


def _parse_warning_payload(value: Any) -> Any:
    candidate = value
    for _ in range(2):
        if not isinstance(candidate, str):
            return candidate
        stripped = candidate.strip()
        if not stripped or stripped[0] not in {'{', '[', '"'}:
            return candidate
        try:
            candidate = json.loads(stripped)
        except json.JSONDecodeError:
            return value
    return candidate


def _summarize_warning_text(value: Any) -> str:
    parsed = _parse_warning_payload(value)
    if isinstance(parsed, dict):
        for key in ("warning", "message", "summary", "detail"):
            text = _clean_text(parsed.get(key))
            if text:
                return _summarize_warning_text(text)
        nested_warnings = parsed.get("warnings")
        if isinstance(nested_warnings, list) and nested_warnings:
            return _summarize_warning_text(nested_warnings[0])
    if isinstance(parsed, list) and parsed:
        return _summarize_warning_text(parsed[0])

    text = _clean_text(parsed)
    if not text:
        return ""

    lowered = text.lower()
    if (
        "does not support multimodal" in lowered
        or "does not support image input" in lowered
        or "configured local model does not support image input" in lowered
    ):
        return "Image interpretation failed because the configured model does not support image input."
    if "invalid json" in lowered:
        return "Image interpretation failed because the model returned invalid JSON."
    if "timed out" in lowered or "timeout" in lowered:
        return "Image interpretation timed out. Radiologist review required."

    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 240:
        return f"{text[:237].rstrip()}..."
    return text


def _warnings_list(value: Any) -> list[str]:
    """Normalize workflow warnings into short strings."""
    if value in (None, ""):
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = [value]

    normalized: list[str] = []
    for item in raw_items:
        text = _summarize_warning_text(item)
        if not text:
            continue
        text = re.sub(r"^(warning|προειδοποίηση)\s*:\s*", "", text, flags=re.IGNORECASE).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _payload_model_to_dict(value: Any) -> dict[str, Any]:
    """Convert pydantic payload fragments to plain dictionaries."""
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        return {key: inner for key, inner in value.items() if inner is not None}
    return {}


def _build_ai_interpretation_summary(payload: RadiologyReportRequest) -> dict[str, Any]:
    """Resolve compact AI context from the new or legacy request shape."""
    compact = _payload_model_to_dict(payload.AIInterpretationSummary)
    if compact:
        compact["warnings"] = _warnings_list(compact.get("warnings"))
        compact["critical_alert"] = bool(compact.get("critical_alert", False))
        compact["findings_count"] = int(compact.get("findings_count") or 0)
        return compact

    legacy = payload.AIInterpretation if isinstance(payload.AIInterpretation, dict) else {}
    findings = legacy.get("findings")
    findings_count = len(findings) if isinstance(findings, list) else 0
    return {
        "status": _coerce_string(legacy.get("status")),
        "critical_alert": bool(legacy.get("critical_alert", False)),
        "summary": _coerce_string(legacy.get("summary")),
        "findings_count": findings_count,
        "warnings": _warnings_list(legacy.get("warnings")),
    }


def _build_qc_summary(payload: RadiologyReportRequest) -> dict[str, Any]:
    """Resolve compact QC context from the new or legacy request shape."""
    compact = _payload_model_to_dict(payload.QC)
    if compact:
        human_review_required = _coerce_bool(compact.get("human_review_required"))
        if human_review_required is not None:
            compact["human_review_required"] = human_review_required
        return compact

    legacy = payload.QCResult if isinstance(payload.QCResult, dict) else {}
    return {
        "qc_status": _coerce_string(legacy.get("qc_status")),
        "issue_type": _coerce_string(legacy.get("issue_type")),
        "recommended_action": _coerce_string(legacy.get("recommended_action")),
        "human_review_required": _coerce_bool(legacy.get("human_review_required")),
        "confidence": _safe_float(legacy.get("confidence")),
    }


def _build_minimal_dicom_context(payload: RadiologyReportRequest) -> dict[str, Any]:
    """Return compact DICOM metadata for prompt building and template selection."""
    dicom = _payload_model_to_dict(payload.DICOM)
    if dicom:
        return dicom
    return {}


def _has_clinical_context(payload: RadiologyReportRequest) -> bool:
    """Return True when optional clinical context is present for template adaptation."""
    if _clean_text(payload.RadiologistNotes):
        return True
    if _clean_text(payload.DoctorNotes):
        return True

    ai_summary = _build_ai_interpretation_summary(payload)
    if (
        ai_summary.get("status")
        or ai_summary.get("summary")
        or ai_summary.get("warnings")
        or (ai_summary.get("findings_count") or 0) > 0
        or ai_summary.get("critical_alert")
    ):
        return True

    qc_summary = _build_qc_summary(payload)
    for key in ("qc_status", "issue_type", "recommended_action", "human_review_required", "confidence"):
        if qc_summary.get(key) not in (None, "", []):
            return True
    return False


def _apply_runtime_signature(
    template_text: str,
    output_language: str,
    signing_physician: str | None,
    signing_physician_code: str | None,
) -> str:
    """Inject the runtime signature block into Greek templates."""
    if output_language != "el":
        return template_text

    signature_block = build_greek_signature_block(signing_physician, signing_physician_code)
    marker = "Ο ΙΑΤΡΟΣ ΑΚΤΙΝΟΛΟΓΟΣ"
    if marker in template_text:
        prefix, _, _ = template_text.rpartition(marker)
        return f"{prefix.rstrip()}\n\n{signature_block}".strip()
    return f"{template_text.rstrip()}\n\n{signature_block}".strip()


def _build_template_response(
    selected_template: ReportTemplate,
    payload: RadiologyReportRequest,
) -> RadiologyTemplateResponse:
    """Return the stored template without AI adaptation."""
    output_language = _resolve_output_language(payload.OutputLanguage)
    signing_physician = _clean_text(payload.SigningPhysician) or None
    signing_physician_code = _clean_text(payload.SigningPhysicianCode) or None
    template_text = _apply_runtime_signature(
        selected_template.text,
        output_language,
        signing_physician,
        signing_physician_code,
    )
    warning_text = build_dicom_order_mismatch_warning_text(payload)
    if warning_text:
        template_text = f"{warning_text}\n\n{template_text}".strip()
    return RadiologyTemplateResponse(
        ID=0,
        TEMPLATE_NAME=selected_template.name,
        TEMPLATE_TEXT=template_text,
        Physician=signing_physician,
    )


def _clean_text(value: Any) -> str:
    """Normalize free-text values for deterministic workflow routes."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _build_runtime_signature_block(
    output_language: str,
    signing_physician: str | None,
    signing_physician_code: str | None,
) -> str:
    if output_language == "el":
        return build_greek_signature_block(signing_physician, signing_physician_code)

    lines = [_SIGNATURE_TITLES.get(output_language, _SIGNATURE_TITLES["en"]), ""]
    lines.append(signing_physician or "______________________")
    if signing_physician_code:
        lines.append(f"({signing_physician_code})")
    return "\n".join(lines)


def _resolve_failure_template_name(
    payload: RadiologyReportRequest,
    resolved_context: Dict[str, Any],
    selected_template: ReportTemplate,
) -> str:
    output_language = _resolve_output_language(payload.OutputLanguage)
    generic_name = _GENERIC_TEMPLATE_NAMES[output_language]
    if selected_template.name and selected_template.name != generic_name:
        return selected_template.name

    for candidate in (
        _clean_text(payload.ExamType),
        _clean_text((resolved_context.get("DICOMSummary") or {}).get("BodyPartExamined")),
        _clean_text(selected_template.name),
        generic_name,
    ):
        if candidate:
            return candidate
    return generic_name


def _resolve_failure_report_title(
    payload: RadiologyReportRequest,
    resolved_context: Dict[str, Any],
    template_name: str,
) -> str:
    dicom_summary = resolved_context.get("DICOMSummary") or {}
    modality = _clean_text(dicom_summary.get("Modality")).upper()
    body_part = _clean_text(dicom_summary.get("BodyPartExamined")).upper()
    exam_type = _clean_text(payload.ExamType)

    if modality in {"CR", "DX", "XR", "XRY"} and body_part:
        return f"{body_part} X-RAY"
    if modality == "CT" and body_part:
        return f"CT {body_part}"
    if exam_type:
        return exam_type
    return template_name


def _detect_laterality(text: str) -> set[str]:
    """Return laterality terms found in the provided text."""
    found: set[str] = set()
    for label, pattern in _LATERALITY_PATTERNS.items():
        if pattern.search(text):
            found.add(label)
    return found


def _tokenize(text: str) -> set[str]:
    """Extract significant lowercase tokens for fuzzy text matching."""
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    return {token for token in tokens if len(token) > 2 and token not in _STOPWORDS}


def _safe_float(value: Any) -> float | None:
    """Coerce a loose value to float when possible."""
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_finding_fields(finding: Any) -> tuple[str, str, str | None, float | None]:
    """Normalize loosely structured AI findings into comparable fields."""
    if isinstance(finding, dict):
        label = _clean_text(finding.get("label") or finding.get("finding_code") or finding.get("finding_text") or "Finding")
        finding_text = _clean_text(finding.get("finding_text") or finding.get("label") or finding.get("finding_code") or label)
        location = _clean_text(finding.get("location")) or None
        confidence = _safe_float(finding.get("confidence"))
        return label, finding_text, location, confidence
    text = _clean_text(finding) or "Finding"
    return text, text, None, None


def _contains_negated_phrase(report_lower: str, phrase: str) -> bool:
    """Detect simple negated mentions such as 'no pneumothorax'."""
    phrase = phrase.strip().lower()
    if not phrase:
        return False
    for prefix in _NEGATION_PREFIXES:
        if f"{prefix} {phrase}" in report_lower or f"{prefix} evidence of {phrase}" in report_lower:
            return True
    return False


def _build_icd10_suggestions(rows: list[Dict[str, Any]]) -> list[Icd10Suggestion]:
    """Convert raw RAG rows into stable response objects."""
    suggestions: list[Icd10Suggestion] = []
    seen: set[str] = set()
    for row in rows:
        code = _clean_text(row.get("code"))
        term = _clean_text(row.get("term"))
        if not code or code in seen:
            continue
        seen.add(code)
        suggestions.append(
            Icd10Suggestion(
                code=code,
                term=term,
                matched_phrase=_clean_text(row.get("matched_phrase")) or None,
            )
        )
    return suggestions


class MedicalImagingService:
    """Owns the full report filling pipeline."""

    def __init__(self) -> None:
        self._ai_client: MedicalAIClient | None = None
        self.rag = RagStore()
        self.project_dir = settings.project_dir
        self._guide_text = self._load_text_file(settings.terms_guide_file)
        self._schema_text = self._load_text_file(settings.output_schema_file)

    def _get_ai_client(self) -> MedicalAIClient:
        """Lazy-initialize the OpenAI client so non-AI endpoints can run without a key."""
        if self._ai_client is None:
            self._ai_client = MedicalAIClient()
        return self._ai_client

    def _load_text_file(self, relative_path: str) -> str:
        """Read a UTF-8 text file from the project root."""
        filepath = _project_path(relative_path)
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Required file not found: {relative_path}")
        with open(filepath, "r", encoding="utf-8") as fh:
            return fh.read()

    def get_terms_summary(self) -> Dict[str, Any]:
        """Return counts of loaded RAG entries WITHOUT calling the AI."""
        return {
            "icd10_count": len(self.rag.icd10),
            "radlex_count": len(self.rag.radlex),
            "embeddings_present": self.rag.embeddings_present(),
        }

    def _resolve_request_context(self, payload: RadiologyReportRequest) -> Dict[str, Any]:
        """Merge top-level metadata with optional DICOM fallback values."""
        dicom = _build_minimal_dicom_context(payload)
        output_language = _resolve_output_language(payload.OutputLanguage)
        accession = _coerce_string(
            _select_first_non_empty(payload.AccessionNumber, get_dicom_value(dicom, "0008,0050"))
        )
        patient_id = _coerce_string(
            _select_first_non_empty(payload.PatientID, get_dicom_value(dicom, "0010,0020"))
        )
        patient_name = _coerce_string(
            _select_first_non_empty(payload.PatientName, get_dicom_value(dicom, "0010,0010"))
        )
        gender = _coerce_string(
            _select_first_non_empty(payload.Gender, get_dicom_value(dicom, "0010,0040"))
        )
        order_id = _coerce_string(
            _select_first_non_empty(
                payload.OrderID,
                get_dicom_value(dicom, "0040,2016"),
                get_dicom_value(dicom, "0040,2017"),
            )
        )

        order_date_value = _select_first_non_empty(payload.OrderDate, parse_dicom_date(get_dicom_value(dicom, "0008,0020")))
        date_of_birth_value = _select_first_non_empty(
            payload.DateOfBirth,
            parse_dicom_date(get_dicom_value(dicom, "0010,0030")),
        )

        order_date = _coerce_iso_datetime(order_date_value)
        date_of_birth = _coerce_iso_datetime(date_of_birth_value)

        dicom_summary = {
            "Modality": _coerce_string(get_dicom_field(dicom, "0008,0060", "Modality")),
            "BodyPartExamined": _coerce_string(get_dicom_field(dicom, "0018,0015", "BodyPartExamined")),
            "StudyDate": _coerce_string(
                _select_first_non_empty(
                    parse_dicom_date(get_dicom_field(dicom, "0008,0020", "StudyDate")),
                    get_dicom_field(dicom, "0008,0020", "StudyDate"),
                )
            ),
            "ViewPosition": _coerce_string(get_dicom_field(dicom, "0018,5101", "ViewPosition")),
            "StudyInstanceUID": _coerce_string(get_dicom_field(dicom, "0020,000D", "StudyInstanceUID")),
            "StudyDescription": _coerce_string(get_dicom_field(dicom, "0008,1030", "StudyDescription")),
            "SeriesDescription": _coerce_string(get_dicom_field(dicom, "0008,103E", "SeriesDescription")),
            "AccessionNumber": accession,
            "DICOMAccessionNumber": _coerce_string(
                _select_first_non_empty(
                    get_dicom_field(dicom, "0008,0050", "DICOMAccessionNumber"),
                    get_dicom_field(dicom, "0008,0050", "AccessionNumber"),
                    accession,
                )
            ),
            "PatientID": patient_id,
            "PatientName": patient_name,
            "PatientSex": gender,
            "Manufacturer": _coerce_string(get_dicom_field(dicom, "0008,0070", "Manufacturer")),
            "ManufacturerModelName": _coerce_string(
                get_dicom_field(dicom, "0008,1090", "ManufacturerModelName")
            ),
        }

        selected_template = select_report_template(
            output_language=output_language,
            modality=dicom_summary.get("Modality"),
            body_part=dicom_summary.get("BodyPartExamined"),
            exam_type=payload.ExamType,
        )

        return {
            "PatientID": patient_id,
            "PatientName": patient_name,
            "OrderID": order_id,
            "OrderDate": order_date,
            "DateOfBirth": date_of_birth,
            "NationalID": _coerce_string(payload.NationalID),
            "Gender": gender,
            "AccessionNumber": accession,
            "OutputLanguage": output_language,
            "ExamType": _coerce_string(payload.ExamType),
            "DICOM": dicom,
            "DICOMSummary": {key: value for key, value in dicom_summary.items() if value not in (None, "")},
            "AIInterpretationSummary": _build_ai_interpretation_summary(payload),
            "QC": _build_qc_summary(payload),
            "SelectedTemplate": {
                "name": selected_template.name,
                "text": selected_template.text,
                "physician": selected_template.physician,
            },
        }

    def _build_model_failure_response(
        self,
        payload: RadiologyReportRequest,
        resolved_context: Dict[str, Any],
        selected_template: ReportTemplate,
    ) -> RadiologyTemplateResponse:
        output_language = _resolve_output_language(payload.OutputLanguage)
        template_name = _resolve_failure_template_name(payload, resolved_context, selected_template)
        title = _resolve_failure_report_title(payload, resolved_context, template_name)
        radiologist_notes = _clean_text(payload.RadiologistNotes)
        signing_physician = _clean_text(payload.SigningPhysician) or None
        signing_physician_code = _clean_text(payload.SigningPhysicianCode) or None
        signature_block = _build_runtime_signature_block(
            output_language,
            signing_physician,
            signing_physician_code,
        )

        if radiologist_notes:
            body_text = radiologist_notes
        else:
            body_text = _apply_runtime_signature(
                selected_template.text,
                output_language,
                signing_physician,
                signing_physician_code,
            )

        template_parts = [title, "", body_text, "", _MODEL_FAILURE_NOTES[output_language]]
        if (
            radiologist_notes
            or _SIGNATURE_TITLES.get(output_language, _SIGNATURE_TITLES["en"]) not in body_text
            and "______________________" not in body_text
        ):
            template_parts.extend(["", signature_block])
        template_text = "\n".join(part for part in template_parts if part is not None).strip()
        mismatch_warning = build_dicom_order_mismatch_warning_text(payload)
        if mismatch_warning and mismatch_warning not in template_text:
            template_text = f"{mismatch_warning}\n\n{template_text}".strip()

        return RadiologyTemplateResponse(
            ID=0,
            TEMPLATE_NAME=template_name,
            TEMPLATE_TEXT=template_text,
            Physician=signing_physician,
        )

    def generate_report_template(self, payload: RadiologyReportRequest) -> RadiologyTemplateResponse:
        """Generate the template-only API response from metadata input."""
        resolved_context = self._resolve_request_context(payload)
        if not resolved_context["AccessionNumber"]:
            raise ValueError("AccessionNumber is required")
        output_language = _resolve_output_language(payload.OutputLanguage)
        selected = select_report_template(
            output_language=output_language,
            modality=(resolved_context.get("DICOMSummary") or {}).get("Modality"),
            body_part=(resolved_context.get("DICOMSummary") or {}).get("BodyPartExamined"),
            exam_type=payload.ExamType,
        )

        if not _has_clinical_context(payload):
            normalized = _build_template_response(selected, payload)
            if settings.persist_output:
                self._save_output(normalized, prefix="report_filling")
            return normalized

        system_prompt = build_report_filling_system_prompt(
            guide_text=self._guide_text,
            schema_text=self._schema_text,
            output_language=output_language,
            selected_template=selected,
        )
        user_prompt = build_report_filling_user_prompt(
            payload,
            resolved_context,
            output_language=output_language,
            selected_template=selected,
        )
        logger.info(
            "Report filling selected_model=%s prompt_length=%d accession=%s language=%s",
            settings.openai_model or "<unset>",
            len(system_prompt) + len(user_prompt),
            resolved_context.get("AccessionNumber"),
            output_language,
        )

        fallback_used = False
        try:
            raw = self._get_ai_client().analyze(system_prompt, user_prompt)
            normalized = normalize_report_template(
                raw=raw,
                payload=payload,
                resolved_context=resolved_context,
                selected_template=selected,
            )
        except Exception as exc:
            fallback_used = True
            logger.warning(
                "Report filling fallback triggered for accession=%s error=%s",
                resolved_context.get("AccessionNumber"),
                exc,
            )
            normalized = self._build_model_failure_response(payload, resolved_context, selected)

        logger.info(
            "Report filling fallback_used=%s accession=%s",
            fallback_used,
            resolved_context.get("AccessionNumber"),
        )

        if settings.persist_output:
            self._save_output(normalized, prefix="report_filling")
        return normalized

    def correct_report(self, payload: ReportCorrectionRequest) -> ReportCorrectionResponse:
        """Restore the legacy workflow contract for report correction."""
        doctor_notes = _clean_text(payload.doctor_notes)
        radiologist_notes = _clean_text(payload.radiologist_notes)
        clinical_report_text = radiologist_notes or doctor_notes

        warnings: list[WorkflowWarning] = []
        doctor_laterality = _detect_laterality(doctor_notes)
        radiologist_laterality = _detect_laterality(radiologist_notes)
        if doctor_laterality and radiologist_laterality and doctor_laterality.isdisjoint(radiologist_laterality):
            warnings.append(
                WorkflowWarning(
                    code="LATERALITY_CONFLICT",
                    message=(
                        "Doctor notes and radiologist notes reference different laterality "
                        f"({', '.join(sorted(doctor_laterality))} vs {', '.join(sorted(radiologist_laterality))})."
                    ),
                    severity="high",
                )
            )

        if not radiologist_notes and doctor_notes:
            warnings.append(
                WorkflowWarning(
                    code="RADIOLOGIST_NOTES_MISSING",
                    message="Radiologist notes were empty, so doctor notes were used as the report text base.",
                    severity="medium",
                )
            )

        icd10_query = " ".join(part for part in [doctor_notes, clinical_report_text, payload.exam_type] if part)
        icd10_codes = _build_icd10_suggestions(self.rag.retrieve_icd10(icd10_query, k=5))
        safety_output = ReportCorrectionSafetyOutput(
            clinical_report=clinical_report_text,
            corrected_radiologist_notes=clinical_report_text,
            corrected_doctor_notes=doctor_notes,
            warnings=warnings,
            rag_grounding={"icd10_codes": [item.model_dump() for item in icd10_codes]},
        )
        return ReportCorrectionResponse(
            clinical_report_text=clinical_report_text,
            confirmed=not any(w.code == "LATERALITY_CONFLICT" for w in warnings),
            warnings=warnings,
            safety_normalized_output=safety_output,
        )

    def match_analysis(self, payload: AnalysisMatchingRequest) -> AnalysisMatchingResponse:
        """Restore the legacy workflow contract for report-vs-AI reconciliation."""
        clinical_report = _clean_text(payload.clinical_report)
        report_lower = clinical_report.lower()
        report_tokens = _tokenize(clinical_report)
        ai_findings = payload.ai_image_analysis.get("findings") or []

        reconciled_findings: list[ReconciledFinding] = []
        warnings: list[WorkflowWarning] = []

        for finding in ai_findings:
            label, finding_text, location, confidence = _extract_finding_fields(finding)
            phrase_candidates = [label, finding_text]
            if location:
                phrase_candidates.append(location)
            candidate_tokens = set().union(*[_tokenize(text) for text in phrase_candidates if text])
            overlap = sorted(candidate_tokens & report_tokens)

            negated = any(_contains_negated_phrase(report_lower, phrase) for phrase in phrase_candidates if phrase)
            label_in_report = label.lower() in report_lower if label else False
            location_in_report = location.lower() in report_lower if location else False
            text_in_report = finding_text.lower() in report_lower if finding_text else False

            if negated:
                match_status = "unmatched"
                in_clinical_report = False
                rationale = "The clinical report appears to negate this AI finding."
            elif text_in_report or (label_in_report and (location_in_report or not location)):
                match_status = "matched"
                in_clinical_report = True
                rationale = "The AI finding is directly described in the clinical report."
            elif overlap:
                match_status = "partial"
                in_clinical_report = True
                rationale = f"Partial overlap found on report terms: {', '.join(overlap[:5])}."
            else:
                match_status = "unmatched"
                in_clinical_report = False
                rationale = "The AI finding was not clearly supported by the clinical report text."

            reconciled_findings.append(
                ReconciledFinding(
                    finding_label=label,
                    finding_text=finding_text,
                    location=location,
                    match_status=match_status,
                    in_clinical_report=in_clinical_report,
                    confidence=confidence,
                    rationale=rationale,
                )
            )

        unmatched_count = sum(1 for item in reconciled_findings if item.match_status == "unmatched")
        if unmatched_count:
            warnings.append(
                WorkflowWarning(
                    code="AI_REPORT_MISMATCH",
                    message=f"{unmatched_count} AI finding(s) were not supported by the clinical report.",
                    severity="medium",
                )
            )

        icd10_query_parts = [clinical_report]
        icd10_query_parts.extend(
            item.finding_text for item in reconciled_findings if item.match_status in {"matched", "partial"}
        )
        suggested_icd10_codes = _build_icd10_suggestions(
            self.rag.retrieve_icd10(" ".join(part for part in icd10_query_parts if part), k=5)
        )

        safety_output = AnalysisMatchingSafetyOutput(
            reconciled_findings=reconciled_findings,
            suggested_icd10_codes=suggested_icd10_codes,
            warnings=warnings,
        )
        return AnalysisMatchingResponse(
            reconciled_findings=reconciled_findings,
            suggested_icd10_codes=suggested_icd10_codes,
            warnings=warnings,
            safety_normalized_output=safety_output,
        )

    def _save_output(self, response: RadiologyTemplateResponse, prefix: str) -> str:
        """Persist the API response (PHI-bearing) as timestamped JSON in ./output."""
        output_dir = _project_path("output")
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{prefix}_{timestamp}.json"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(response.model_dump(mode="json"), fh, indent=2)
        logger.info("Saved output to %s", filepath)
        return filepath
