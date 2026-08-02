from __future__ import annotations

import zipfile
import logging
from pathlib import Path
from typing import Any
import re

import numpy as np
import pydicom  # type: ignore
from PIL import Image
from pydicom.misc import is_dicom  # type: ignore

from ..config import Settings
from ..dicom_utils import extract_dicom_metadata, find_dicom_files
from ..model_resolver import model_supports_vision
from ..protocol_classifier import SUPPORTED_EXAMS, ExamClassification, classify_exam_type
from .models import AIInfo, Finding, InterpretationResponse, StudyInfo
from .xray_model import STRONG_THRESHOLD, WEAK_THRESHOLD, run_xray_model
from ..audit import log_interpretation


_VIEW_WORD_RE = re.compile(r"(^|\s)(pa|ap)(\s|$)", re.IGNORECASE)
_TWO_VIEWS_RE = re.compile(r"(\b2\b|two)\s*view", re.IGNORECASE)

logger = logging.getLogger(__name__)

BILATERAL_BODY_PARTS = {
    "ABDOMEN",
    "CHEST",
    "SPINE",
    "SPINE_LUMBAR",
    "SPINE_THORACIC",
    "SPINE_CERVICAL",
    "KUB",
    "PELVIS",
    "KIDNEY",
}

_CHEST_PRIORITY_FINDING_CODES = {
    "PNEUMOTHORAX",
    "PLEURAL_EFFUSION",
    "CONSOLIDATION",
    "PULMONARY_OPACITY",
    "LUNG_OPACITY",
    "LOWER_ZONE_OPACITY",
    "PNEUMONIA",
    "INFILTRATION",
    "ATELECTASIS",
    "PULMONARY_EDEMA",
    "CARDIOMEGALY",
    "PULMONARY_NODULE",
    "NODULE",
    "MASS",
    "FRACTURE",
    "RIB_FRACTURE",
    "CLAVICLE_FRACTURE",
    "SCAPULAR_FRACTURE",
    "STERNUM_FRACTURE",
    "THORACIC_SPINE_FRACTURE",
}

_CHEST_SUPPORT_DEVICE_CODES = {
    "CHEST_TUBE",
    "PLEURAL_DRAIN",
    "CENTRAL_LINE",
    "PICC_LINE",
    "CVC",
    "PORT",
    "ENDOTRACHEAL_TUBE",
    "TRACHEOSTOMY_TUBE",
    "NG_TUBE",
    "ENTERIC_TUBE",
    "PACEMAKER",
}

_CHEST_RELEVANT_KEYWORDS = {
    "lung",
    "pulmonary",
    "pleura",
    "pleural",
    "pneumothorax",
    "effusion",
    "cardiomediastinal",
    "cardiac",
    "heart",
    "mediastin",
    "hilar",
    "perihilar",
    "diaphragm",
    "costophrenic",
    "cp angle",
    "rib",
    "clavicle",
    "scapula",
    "scapular",
    "sternum",
    "sternotomy",
    "thoracic",
    "chest wall",
    "apex",
    "basilar",
    "lower lung zone",
    "upper lung zone",
    "mid lung zone",
    "central line",
    "picc",
    "cvc",
    "port",
    "endotracheal",
    "tracheostomy",
    "chest tube",
    "pleural drain",
    "mediastinal drain",
}

_CHEST_OFF_TARGET_KEYWORDS = {
    "abdomen",
    "abdominal",
    "renal",
    "kidney",
    "ureter",
    "ureteric",
    "bladder",
    "pelvis",
    "pelvic",
    "lumbar",
    "lumbosacral",
    "iliac",
    "sacrum",
    "sacral",
    "hip",
    "femur",
    "bowel",
    "nephrostomy",
}

_CHEST_OFF_TARGET_FINDING_CODES = {
    "URETERIC_STENT",
    "NEPHROSTOMY_TUBE",
    "CONTRAST_OPACIFIED_BLADDER",
}

_SUPPORTED_OUTPUT_LANGUAGES = {"el", "en", "ar"}

_DISCLAIMER_BY_LANGUAGE = {
    "el": "Βοηθητικό σύστημα AI μόνο. Απαιτείται έλεγχος από ακτινολόγο. Δεν προορίζεται για τελική διάγνωση.",
    "en": "Assistive AI only. Radiologist review required. Not for final diagnosis.",
    "ar": "هذا النظام للذكاء الاصطناعي المساعد فقط. يلزم مراجعة اختصاصي الأشعة. غير مخصص للتشخيص النهائي.",
}

_TEXT_TRANSLATIONS = {
    "el": {
        "No AI candidate acute finding identified above configured thresholds. Radiologist review required.": (
            "Δεν εντοπίστηκε οξύ εύρημα υποψήφιο από το AI πάνω από τα καθορισμένα όρια. Απαιτείται αξιολόγηση από ακτινολόγο."
        ),
        "Low-confidence AI candidate finding detected. Radiologist review required.": (
            "Εντοπίστηκε εύρημα χαμηλής βεβαιότητας από το AI. Απαιτείται αξιολόγηση από ακτινολόγο."
        ),
        "One AI candidate finding detected. Radiologist review required.": (
            "Εντοπίστηκε ένα πιθανό εύρημα από το AI. Απαιτείται αξιολόγηση από ακτινολόγο."
        ),
        "Unsupported or unreadable image file. Radiologist review required.": (
            "Μη υποστηριζόμενο ή μη αναγνώσιμο αρχείο εικόνας. Απαιτείται αξιολόγηση από ακτινολόγο."
        ),
        "X-ray interpretation model inference failed. Radiologist review required.": (
            "Η εκτέλεση του μοντέλου ερμηνείας ακτινογραφίας απέτυχε. Απαιτείται αξιολόγηση από ακτινολόγο."
        ),
        "Unsupported modality for this service. Radiologist review required.": (
            "Μη υποστηριζόμενη modality για αυτή την υπηρεσία. Απαιτείται αξιολόγηση από ακτινολόγο."
        ),
        "Unsupported exam type for X-ray MVP interpretation.": (
            "Μη υποστηριζόμενος τύπος εξέτασης για την MVP ερμηνεία ακτινογραφίας."
        ),
        "Single frontal image reviewed; lateral view not available.": (
            "Ανασκοπήθηκε μία μόνο μετωπιαία εικόνα· δεν ήταν διαθέσιμη πλάγια λήψη."
        ),
        "Image quality limitations reported by model; interpret findings cautiously.": (
            "Το μοντέλο ανέφερε περιορισμούς στην ποιότητα εικόνας· ερμηνεύστε τα ευρήματα με προσοχή."
        ),
        "Out-of-scope chest candidate findings suppressed from main findings.": (
            "Υποψήφια ευρήματα θώρακος εκτός πεδίου καταστάλθηκαν από τα κύρια ευρήματα."
        ),
        "Body part mismatch: selected series not appropriate for abdominal-organ interpretation.": (
            "Ασυμφωνία ανατομικής περιοχής: η επιλεγμένη σειρά δεν είναι κατάλληλη για ερμηνεία κοιλιακών οργάνων."
        ),
        "CT interpretation requires OPENAI_API_KEY to be configured. Radiologist review required.": (
            "Η ερμηνεία CT απαιτεί ρυθμισμένο OPENAI_API_KEY. Απαιτείται αξιολόγηση από ακτινολόγο."
        ),
        "Zip file rejected for security reasons. Radiologist review required.": (
            "Το αρχείο zip απορρίφθηκε για λόγους ασφαλείας. Απαιτείται αξιολόγηση από ακτινολόγο."
        ),
        "Uploaded file is not a DICOM file or zip archive. Radiologist review required.": (
            "Το μεταφορτωμένο αρχείο δεν είναι DICOM ή συμπιεσμένο αρχείο zip. Απαιτείται αξιολόγηση από ακτινολόγο."
        ),
        "No DICOM files found in upload. Radiologist review required.": (
            "Δεν βρέθηκαν αρχεία DICOM στη μεταφόρτωση. Απαιτείται αξιολόγηση από ακτινολόγο."
        ),
        "No CT slices could be decoded from the uploaded DICOM. Radiologist review required.": (
            "Δεν ήταν δυνατή η αποκωδικοποίηση τομών CT από το μεταφορτωμένο DICOM. Απαιτείται αξιολόγηση από ακτινολόγο."
        ),
        "CT interpretation model inference failed. Radiologist review required.": (
            "Η εκτέλεση του μοντέλου ερμηνείας CT απέτυχε. Απαιτείται αξιολόγηση από ακτινολόγο."
        ),
    },
    "ar": {
        "No AI candidate acute finding identified above configured thresholds. Radiologist review required.": (
            "لم يتم تحديد أي نتيجة حادة مرشحة من الذكاء الاصطناعي فوق الحدود المضبوطة. يلزم مراجعة اختصاصي الأشعة."
        ),
        "Low-confidence AI candidate finding detected. Radiologist review required.": (
            "تم اكتشاف نتيجة مرشحة منخفضة الثقة من الذكاء الاصطناعي. يلزم مراجعة اختصاصي الأشعة."
        ),
        "One AI candidate finding detected. Radiologist review required.": (
            "تم اكتشاف نتيجة مرشحة واحدة من الذكاء الاصطناعي. يلزم مراجعة اختصاصي الأشعة."
        ),
        "Unsupported or unreadable image file. Radiologist review required.": (
            "ملف الصورة غير مدعوم أو غير قابل للقراءة. يلزم مراجعة اختصاصي الأشعة."
        ),
        "X-ray interpretation model inference failed. Radiologist review required.": (
            "فشل استنتاج نموذج تفسير الأشعة السينية. يلزم مراجعة اختصاصي الأشعة."
        ),
        "Unsupported modality for this service. Radiologist review required.": (
            "نوع التصوير غير مدعوم لهذه الخدمة. يلزم مراجعة اختصاصي الأشعة."
        ),
        "Unsupported exam type for X-ray MVP interpretation.": (
            "نوع الفحص غير مدعوم لتفسير الأشعة السينية في هذه النسخة."
        ),
        "Single frontal image reviewed; lateral view not available.": (
            "تمت مراجعة صورة أمامية واحدة فقط؛ العرض الجانبي غير متاح."
        ),
        "Image quality limitations reported by model; interpret findings cautiously.": (
            "أبلغ النموذج عن محدودية في جودة الصورة؛ يجب تفسير النتائج بحذر."
        ),
        "Out-of-scope chest candidate findings suppressed from main findings.": (
            "تمت إزالة نتائج الصدر خارج النطاق من النتائج الرئيسية."
        ),
        "Body part mismatch: selected series not appropriate for abdominal-organ interpretation.": (
            "عدم تطابق في الجزء التشريحي: السلسلة المختارة غير مناسبة لتفسير أعضاء البطن."
        ),
        "CT interpretation requires OPENAI_API_KEY to be configured. Radiologist review required.": (
            "يتطلب تفسير CT ضبط OPENAI_API_KEY. يلزم مراجعة اختصاصي الأشعة."
        ),
        "Zip file rejected for security reasons. Radiologist review required.": (
            "تم رفض ملف zip لأسباب أمنية. يلزم مراجعة اختصاصي الأشعة."
        ),
        "Uploaded file is not a DICOM file or zip archive. Radiologist review required.": (
            "الملف المرفوع ليس ملف DICOM أو أرشيف zip. يلزم مراجعة اختصاصي الأشعة."
        ),
        "No DICOM files found in upload. Radiologist review required.": (
            "لم يتم العثور على ملفات DICOM في الرفع. يلزم مراجعة اختصاصي الأشعة."
        ),
        "No CT slices could be decoded from the uploaded DICOM. Radiologist review required.": (
            "تعذر فك ترميز مقاطع CT من ملف DICOM المرفوع. يلزم مراجعة اختصاصي الأشعة."
        ),
        "CT interpretation model inference failed. Radiologist review required.": (
            "فشل استنتاج نموذج تفسير CT. يلزم مراجعة اختصاصي الأشعة."
        ),
    },
}


def _audit(response: InterpretationResponse, clinical_indication: str | None) -> InterpretationResponse:
    from ..audit import log_interpretation

    log_interpretation(
        study_instance_uid=response.study.study_instance_uid,
        exam_type=response.exam_type,
        status=response.status,
        finding_codes=[f.finding_code for f in response.findings],
        critical_alert=response.critical_alert,
        model_name=response.ai.model_name,
        modality_handled=response.ai.modality_handled,
        clinical_indication=clinical_indication,
        warnings=response.warnings,
    )
    return response


def normalize_output_language(output_language: str | None) -> str:
    language = (output_language or "el").strip().lower()
    return language if language in _SUPPORTED_OUTPUT_LANGUAGES else "el"


def _translate_text(text: str | None, output_language: str) -> str:
    value = str(text or "").strip()
    language = normalize_output_language(output_language)
    if not value or language == "en":
        return value
    translated = _TEXT_TRANSLATIONS.get(language, {}).get(value)
    if translated:
        return translated
    return value


def _human_label_from_code(code: str, output_language: str) -> str:
    language = normalize_output_language(output_language)
    base = (code or "OTHER_FINDING").strip().upper()
    if language == "el":
        mapping = {
            "PULMONARY_NODULE": "πιθανό πνευμονικό οζίδιο",
            "PNEUMOTHORAX": "πιθανός πνευμοθώρακας",
            "PLEURAL_EFFUSION": "πιθανή υπεζωκοτική συλλογή",
            "CONSOLIDATION": "πιθανή πύκνωση",
            "LOWER_ZONE_OPACITY": "πιθανή σκίαση στη χαμηλή πνευμονική ζώνη",
            "CARDIOMEGALY": "πιθανή ήπια διεύρυνση της καρδιακής σκιάς",
            "PULMONARY_OPACITY": "πιθανή πνευμονική σκίαση",
        }
        return mapping.get(base, base.replace("_", " ").lower())
    if language == "ar":
        mapping = {
            "PULMONARY_NODULE": "عقدة رئوية محتملة",
            "PNEUMOTHORAX": "استرواح صدر محتمل",
            "PLEURAL_EFFUSION": "انصباب جنبي محتمل",
            "CONSOLIDATION": "تكثف محتمل",
            "LOWER_ZONE_OPACITY": "عتامة محتملة في المنطقة الرئوية السفلية",
            "CARDIOMEGALY": "تضخم محتمل وخفيف في ظل القلب",
            "PULMONARY_OPACITY": "عتامة رئوية محتملة",
        }
        return mapping.get(base, base.replace("_", " ").lower())
    return base.replace("_", " ").lower()


def _localize_finding(finding: Finding, output_language: str) -> Finding:
    language = normalize_output_language(output_language)
    if language == "en":
        return finding
    label = _human_label_from_code(finding.finding_code, language)
    if language == "ar":
        location = f" في {finding.location}" if finding.location else ""
        text = f"{label}{location}. يلزم مراجعة اختصاصي الأشعة."
    else:
        location = f" στη θέση {finding.location}" if finding.location else ""
        text = f"{label.capitalize()}{location}. Απαιτείται αξιολόγηση από ακτινολόγο."
    return finding.model_copy(update={"finding_text": text})


def _localize_warning_text(text: str, output_language: str) -> str:
    translated = _translate_text(text, output_language)
    if translated != text:
        return translated
    language = normalize_output_language(output_language)
    if language == "el":
        return f"Προειδοποίηση: {text}"
    if language == "ar":
        return f"تحذير: {text}"
    return text


def localize_disclaimer_text(output_language: str) -> str:
    return _DISCLAIMER_BY_LANGUAGE[normalize_output_language(output_language)]


def localize_response(response: InterpretationResponse, output_language: str) -> InterpretationResponse:
    language = normalize_output_language(output_language)
    if language == "en":
        return response
    localized_findings = [_localize_finding(finding, language) for finding in response.findings]
    localized_incidental_findings = [
        _localize_finding(finding, language) for finding in response.incidental_or_off_target_findings
    ]
    localized_warnings = [_localize_warning_text(text, language) for text in response.warnings]
    localized_summary = _translate_text(response.summary, language)
    localized_disclaimer = localize_disclaimer_text(language)
    return response.model_copy(
        update={
            "findings": localized_findings,
            "incidental_or_off_target_findings": localized_incidental_findings,
            "summary": localized_summary,
            "warnings": localized_warnings,
            "disclaimer": localized_disclaimer,
        }
    )


def _expected_views_from_study_description(study_description: str | None) -> int | None:
    if not study_description:
        return None
    text = study_description.strip()
    if _TWO_VIEWS_RE.search(text):
        return 2
    m = re.search(r"(\b\d+\b)\s*views?", text, flags=re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None


def _expected_view_count(study_description: str | None) -> int | None:
    if not study_description:
        return None
    desc = study_description.lower()
    if "2 or more" in desc or "2+ views" in desc:
        return 2
    m = re.search(r"(\d+)\s+view", desc)
    if m:
        return int(m.group(1))
    return None


def _check_indication_mismatch(
    clinical_indication: str | None,
    exam_type: str,
) -> str | None:
    """
    Returns a warning string if the clinical indication is anatomically
    inconsistent with the exam type, else None.
    """
    if not clinical_indication:
        return None
    ind = clinical_indication.lower()
    respiratory_keywords = [
        "shortness of breath",
        "sob",
        "dyspnea",
        "cough",
        "wheeze",
        "chest pain",
        "respiratory",
        "breathing",
        "pneumonia",
    ]
    non_chest_exam = exam_type.startswith("XR_") and not exam_type.startswith("XR_CHEST")
    if non_chest_exam and any(kw in ind for kw in respiratory_keywords):
        return (
            f"Clinical indication '{clinical_indication}' suggests a respiratory "
            f"complaint but exam type is {exam_type}. "
            "Verify correct patient/order before acting on AI findings."
        )
    return None


def _norm_meta(text: str | None) -> str:
    return (text or "").lower().replace("\\", " ").replace("/", " ").replace("-", " ")


def _view_from_text(text: str) -> str | None:
    if not text:
        return None
    padded = f" {text} "
    if _VIEW_WORD_RE.search(padded):
        if re.search(r"(^|\s)pa(\s|$)", padded, flags=re.IGNORECASE):
            return "PA"
        if re.search(r"(^|\s)ap(\s|$)", padded, flags=re.IGNORECASE):
            return "AP"
    if "lateral" in text or " lat " in padded:
        return "LATERAL"
    return None


def _detect_view_from_metadata(metadata: dict[str, Any]) -> tuple[str, str, float]:
    """
    Returns (view_detected, view_source, view_confidence).
    """
    vp = (metadata.get("view_position") or "").strip().upper()
    if vp in {"PA", "AP"}:
        return vp, "metadata:ViewPosition", 1.0

    combined = " ".join(
        [
            _norm_meta(metadata.get("series_description")),
            _norm_meta(metadata.get("protocol_name")),
            _norm_meta(metadata.get("study_description")),
            _norm_meta(metadata.get("performed_protocol_codes")),
        ]
    ).strip()

    v = _view_from_text(combined)
    if v in {"PA", "AP"}:
        return v, "metadata:text_derived", 0.9

    return "UNKNOWN", "unknown", 0.0


def _extract_available_views(dicom_files: list[Path]) -> list[str]:
    views: list[str] = []
    for fp in dicom_files:
        try:
            ds = pydicom.dcmread(str(fp), stop_before_pixels=True, force=True)
            v = str(getattr(ds, "ViewPosition", "") or "").strip().upper()
            if v in {"PA", "AP", "LATERAL"} and v not in views:
                views.append(v)
        except Exception:
            continue
    return views


def _zone_location_from_lobe(location: str) -> tuple[str, bool]:
    loc = (location or "").strip()
    low = loc.lower()
    if "lower lobe" in low:
        return low.replace("lower lobe", "lower lung zone"), True
    if "upper lobe" in low:
        return low.replace("upper lobe", "upper lung zone"), True
    if "middle lobe" in low:
        return low.replace("middle lobe", "mid lung zone"), True
    return loc, False


def _normalize_model_laterality(raw: Any) -> str | None:
    if raw is None:
        return None
    v = str(raw).strip().upper()
    if v == "L":
        return "LEFT"
    if v == "R":
        return "RIGHT"
    return None


def _finding_log_payload(findings: list[Finding]) -> list[dict[str, Any]]:
    return [finding.model_dump(mode="json") for finding in findings]


def _contains_any_keyword(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _finding_text_blob(finding: Finding) -> str:
    return " ".join(
        part
        for part in [
            finding.finding_code,
            finding.location or "",
            finding.finding_text or "",
        ]
        if part
    ).lower()


def _is_off_target_xr_chest_finding(finding: Finding) -> bool:
    code = (finding.finding_code or "").strip().upper()
    blob = _finding_text_blob(finding)
    confidence = float(finding.confidence or 0.0)
    chest_relevant = (
        code in _CHEST_PRIORITY_FINDING_CODES
        or code in _CHEST_SUPPORT_DEVICE_CODES
        or _contains_any_keyword(blob, _CHEST_RELEVANT_KEYWORDS)
    )
    off_target = code in _CHEST_OFF_TARGET_FINDING_CODES or _contains_any_keyword(blob, _CHEST_OFF_TARGET_KEYWORDS)
    if off_target and not (chest_relevant and confidence >= 0.90):
        return True
    if code in {"SURGICAL_HARDWARE", "SURGICAL_CLIPS", "IMPLANTED_DEVICE", "VASCULAR_DEVICE"} and not chest_relevant:
        return True
    return False


def _postprocess_xr_findings(
    *,
    findings: list[Finding],
    exam_type: str,
    final_view: str | None,
    single_frontal_only: bool,
) -> tuple[list[Finding], list[Finding]]:
    if not exam_type.startswith("XR_CHEST"):
        return findings, []

    logger.info("XR_CHEST original model findings=%s", _finding_log_payload(findings))

    filtered_findings: list[Finding] = []
    incidental_findings: list[Finding] = []
    for finding in findings:
        code = (getattr(finding, "finding_code", "") or "").upper()
        location = getattr(finding, "location", None)
        confidence = float(getattr(finding, "confidence", 0.0) or 0.0)
        finding_text = getattr(finding, "finding_text", "")
        priority = getattr(finding, "priority", "ROUTINE")

        if single_frontal_only and isinstance(location, str) and "lobe" in location.lower():
            new_loc, changed = _zone_location_from_lobe(location)
            if changed:
                location = new_loc
                confidence = min(confidence, 0.55)

        if code == "CARDIOMEGALY":
            priority = "ROUTINE"
            if final_view == "AP":
                confidence = min(confidence, 0.55)
                finding_text = "Possible apparent enlargement of the cardiac silhouette (AP projection may magnify heart size). Radiologist review required."
            elif final_view == "PA":
                confidence = min(confidence, 0.60)
                finding_text = "Possible mild enlargement of the cardiac silhouette. Radiologist review required."
            else:
                confidence = min(confidence, 0.55)
                finding_text = "Possible mild enlargement of the cardiac silhouette. Radiologist review required."

        if code in {"PULMONARY_OPACITY", "LUNG_OPACITY", "CONSOLIDATION", "PNEUMONIA", "INFILTRATION"}:
            if single_frontal_only:
                confidence = min(confidence, 0.45 if confidence < 0.70 else 0.55)
            if confidence < 0.35:
                continue
            if single_frontal_only and code in {"PULMONARY_OPACITY", "LUNG_OPACITY"} and confidence <= 0.55:
                code = "LOWER_ZONE_OPACITY"
                if isinstance(location, str) and location.strip():
                    location = location.strip()
                else:
                    location = "lower lung zone"
                finding_text = "Questionable mild basilar opacity or vascular crowding. Radiologist review required."

        candidate = finding.model_copy(
            update={
                "finding_code": code,
                "location": location,
                "confidence": confidence,
                "finding_text": finding_text,
                "priority": priority,
            }
        )
        if _is_off_target_xr_chest_finding(candidate):
            incidental_findings.append(candidate)
            continue
        filtered_findings.append(candidate)

    logger.info("XR_CHEST filtered findings=%s", _finding_log_payload(filtered_findings))
    logger.info("XR_CHEST moved incidental/off-target findings=%s", _finding_log_payload(incidental_findings))
    return filtered_findings, incidental_findings

def build_summary(findings: list[Finding], output_language: str = "en") -> str:
    language = normalize_output_language(output_language)
    if not findings:
        text = (
            "No AI candidate acute finding identified above configured thresholds. "
            "Radiologist review required."
        )
        return _translate_text(text, language)

    has_standard = any((f.confidence or 0.0) >= STRONG_THRESHOLD for f in findings)
    if not has_standard:
        return _translate_text(
            "Low-confidence AI candidate finding detected. Radiologist review required.",
            language,
        )

    if len(findings) == 1:
        return _translate_text("One AI candidate finding detected. Radiologist review required.", language)
    if language == "el":
        return f"Εντοπίστηκαν {len(findings)} πιθανά ευρήματα από το AI. Απαιτείται αξιολόγηση από ακτινολόγο."
    if language == "ar":
        return f"تم اكتشاف {len(findings)} نتائج مرشحة من الذكاء الاصطناعي. يلزم مراجعة اختصاصي الأشعة."
    return f"{len(findings)} AI candidate findings detected. Radiologist review required."


def has_critical(findings: list[Finding]) -> bool:
    return any(f.priority == "CRITICAL" for f in findings)


def _load_upload_to_dicom_dir(upload_path: Path, dicom_dir: Path) -> list[Path]:
    dicom_dir.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(upload_path):
        with zipfile.ZipFile(upload_path, "r") as zf:
            resolved_base = dicom_dir.resolve()
            for member in zf.namelist():
                target = (dicom_dir / member).resolve()
                if not str(target).startswith(str(resolved_base)):
                    raise ValueError(f"Unsafe zip entry (path traversal attempt): {member}")
            zf.extractall(dicom_dir)
        return find_dicom_files(dicom_dir)
    single = dicom_dir / "upload.dcm"
    single.write_bytes(upload_path.read_bytes())
    return [single]


def _load_upload_to_png(upload_path: Path, png_path: Path) -> None:
    """
    Accept common image formats (png/jpg/jpeg/webp/bmp/tiff/...) and normalize to PNG.
    """
    img = Image.open(str(upload_path))
    # If multi-frame (e.g., GIF), take the first frame.
    try:
        img.seek(0)
    except Exception:
        pass
    img = img.convert("RGB")
    img.save(str(png_path), format="PNG")


def _should_use_gpt(settings: Settings) -> bool:
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        return False
    import os

    running_pytest = "PYTEST_CURRENT_TEST" in os.environ
    return (not running_pytest) or api_key.startswith("sk-test")


def _selected_vision_model(settings: Settings) -> str:
    return settings.vision_model.strip()


def _supports_configured_vision_model(settings: Settings) -> bool | None:
    selected_model = _selected_vision_model(settings)
    if not selected_model:
        return None
    return model_supports_vision(selected_model)


def _should_skip_image_model(settings: Settings) -> tuple[bool, str | None, str]:
    selected_model = _selected_vision_model(settings)
    supports_vision = _supports_configured_vision_model(settings)
    logger.info(
        "Image interpretation config selected_model=%s supports_vision=%s enable_image_model=%s",
        selected_model or "<unset>",
        supports_vision,
        settings.enable_image_model,
    )

    if not settings.enable_image_model:
        return True, selected_model or None, "Image interpretation is disabled by ENABLE_IMAGE_MODEL=false."
    if _should_use_gpt(settings) and not selected_model:
        return True, None, "VISION_MODEL is not configured for image interpretation."
    if selected_model and supports_vision is False:
        return True, selected_model, "Configured model does not support image input."
    return False, selected_model or None, ""


def _build_review_required_response(
    *,
    exam_type: str,
    summary: str,
    warnings: list[str],
    output_language: str,
    settings: Settings,
    clinical_indication: str | None,
    study: StudyInfo | None = None,
    model_name: str | None = None,
) -> InterpretationResponse:
    response = InterpretationResponse(
        exam_type=exam_type,
        status="REVIEW_REQUIRED",
        findings=[],
        critical_alert=False,
        summary=summary,
        study=study or StudyInfo(),
        ai=AIInfo(
            model_name=model_name or "unknown",
            modality_handled="XRAY",
            slices_reviewed=1,
            not_for_medical_use=True,
        ),
        warnings=warnings,
        disclaimer=settings.disclaimer_text,
    )
    return _audit(localize_response(response, output_language), clinical_indication)


def build_image_response(
    *,
    upload_input_path: Path,
    workdir: Path,
    clinical_indication: str | None,
    settings: Settings,
    output_language: str = "el",
    exam_type: str = "XR_CHEST",
) -> InterpretationResponse:
    image_path = workdir / "xray_input.png"
    warnings: list[str] = []
    skip_image_model, selected_vision_model, skip_reason = _should_skip_image_model(settings)
    mismatch_warning = _check_indication_mismatch(clinical_indication, exam_type)
    if mismatch_warning:
        logger.warning(mismatch_warning)
        warnings.append(mismatch_warning)

    try:
        _load_upload_to_png(upload_input_path, image_path)
    except Exception as e:
        reason = str(e) or e.__class__.__name__
        study = StudyInfo(image_quality="UNREADABLE")
        return _build_review_required_response(
            exam_type=exam_type,
            summary="Unsupported or unreadable image file. Radiologist review required.",
            warnings=[*warnings, reason],
            output_language=output_language,
            settings=settings,
            clinical_indication=clinical_indication,
            study=study,
        )

    if skip_image_model and not exam_type.startswith("XR_CHEST"):
        return _build_review_required_response(
            exam_type=exam_type,
            summary=(
                "Image interpretation was skipped because the configured local model does not support image input. "
                "Radiologist review required."
            ),
            warnings=[*warnings, skip_reason],
            output_language=output_language,
            settings=settings,
            clinical_indication=clinical_indication,
            study=StudyInfo(image_quality="UNKNOWN"),
            model_name=selected_vision_model,
        )

    try:
        if exam_type.startswith("XR_CHEST"):
            # Chest: always use the purpose-built local CNN (accurate + free).
            findings, model_outputs, model_meta = run_xray_model(str(image_path), exam_type)
        elif _should_use_gpt(settings) and selected_vision_model:
            # Non-chest: no local CNN, fall back to the configured vision model
            # (Ollama or OpenAI, per OPENAI_BASE_URL / VISION_MODEL).
            from .gpt_xray_model import run_gpt_xray_model

            findings, _gpt_output, model_meta = run_gpt_xray_model(
                image_path=str(image_path),
                exam_type=exam_type,
                output_language=output_language,
                openai_api_key=(settings.openai_api_key or "").strip(),
                openai_base_url=settings.openai_base_url,
                openai_model=selected_vision_model,
                vision_image_url_as_string=settings.vision_image_url_as_string,
                openai_timeout=settings.openai_timeout,
                study_description=None,
                series_description=None,
                laterality=None,
                view=None,
            )
            model_outputs = {}
        else:
            raise RuntimeError(
                "No local model available for this body part; configure OPENAI_API_KEY to enable full X-ray coverage."
            )
    except Exception as e:
        reason = str(e) or e.__class__.__name__
        study = StudyInfo(image_quality="UNREADABLE")
        if reason == "No local model available for this body part; configure OPENAI_API_KEY to enable full X-ray coverage.":
            return _build_review_required_response(
                exam_type=exam_type,
                summary=build_summary([], output_language),
                warnings=[*warnings, reason],
                output_language=output_language,
                settings=settings,
                clinical_indication=clinical_indication,
                study=study,
                model_name=selected_vision_model,
            )
        return _build_review_required_response(
            exam_type=exam_type,
            summary="X-ray interpretation model inference failed. Radiologist review required.",
            warnings=[*warnings, reason],
            output_language=output_language,
            settings=settings,
            clinical_indication=clinical_indication,
            study=study,
            model_name=selected_vision_model,
        )

    study = StudyInfo(image_quality=str(model_meta.get("image_quality") or "UNKNOWN"))
    model_lat = _normalize_model_laterality(model_meta.get("laterality_from_image"))
    if model_lat:
        study.laterality = model_lat
    findings, incidental_findings = _postprocess_xr_findings(
        findings=findings,
        exam_type=exam_type,
        final_view=str(model_meta.get("view_detected") or "").upper() or None,
        single_frontal_only=False,
    )
    ai = AIInfo(
        model_name=str(model_meta.get("name") or selected_vision_model or "unknown"),
        modality_handled="XRAY",
        slices_reviewed=1,
        not_for_medical_use=True,
    )
    return _audit(localize_response(InterpretationResponse(
        exam_type=exam_type,
        status="COMPLETED",
        findings=findings,
        incidental_or_off_target_findings=incidental_findings,
        critical_alert=has_critical(findings),
        summary=build_summary(findings, output_language),
        study=study,
        ai=ai,
        warnings=warnings,
        disclaimer=settings.disclaimer_text,
    ), output_language), clinical_indication)


def _dicom_to_png(dicom_path: Path, png_path: Path) -> None:
    dicom_to_png(dicom_path, png_path)


def dicom_to_png(dicom_path: Path, output_path: Path) -> None:
    ds = pydicom.dcmread(str(dicom_path), force=True)
    if not hasattr(ds, "pixel_array"):
        raise RuntimeError("DICOM pixel data not found")

    arr = ds.pixel_array  # type: ignore[attr-defined]
    arr = np.asarray(arr).astype(np.float32)
    if arr.ndim > 2:
        # Multi-frame: take first frame.
        arr = arr[0]

    # Apply RescaleSlope/RescaleIntercept if present.
    try:
        slope = float(getattr(ds, "RescaleSlope", 1.0) or 1.0)
        intercept = float(getattr(ds, "RescaleIntercept", 0.0) or 0.0)
        arr = (arr * slope) + intercept
    except Exception:
        pass

    # Common in x-ray: MONOCHROME1 means higher values should be displayed darker.
    try:
        if (getattr(ds, "PhotometricInterpretation", "") or "").upper() == "MONOCHROME1":
            arr = np.nanmax(arr) - arr
    except Exception:
        pass

    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        raise RuntimeError("DICOM pixel data invalid (no finite values)")

    # Robust normalization using 1st and 99th percentile clipping.
    p1 = float(np.percentile(finite, 1))
    p99 = float(np.percentile(finite, 99))
    if p99 <= p1:
        # Fallback to min/max
        p1 = float(np.min(finite))
        p99 = float(np.max(finite))
        if p99 <= p1:
            p99 = p1 + 1.0

    arr = np.clip(arr, p1, p99)
    arr = (arr - p1) / (p99 - p1)
    arr = (arr * 255.0).clip(0, 255).astype(np.uint8)
    Image.fromarray(arr).save(str(output_path))


def build_dicom_response(
    *,
    upload_input_path: Path,
    workdir: Path,
    clinical_indication: str | None,
    output_language: str = "el",
    settings: Settings,
) -> InterpretationResponse:
    skip_image_model, selected_vision_model, skip_reason = _should_skip_image_model(settings)
    # Support non-DICOM image uploads (png/jpg/jpeg/...) in the same endpoint.
    if (
        (not zipfile.is_zipfile(upload_input_path))
        and (not is_dicom(str(upload_input_path)))
        and (upload_input_path.suffix.lower() != ".dcm")
    ):
        return build_image_response(
            upload_input_path=upload_input_path,
            workdir=workdir,
            clinical_indication=clinical_indication,
            output_language=output_language,
            settings=settings,
            exam_type="XR_CHEST",
        )

    dicom_dir = workdir / "dicom"
    dicom_files = _load_upload_to_dicom_dir(upload_input_path, dicom_dir)
    if len(dicom_files) > 1:
        logger.warning(
            "Zip contains %d DICOM files; only the first will be used for interpretation (MVP behaviour).",
            len(dicom_files),
        )
    if not dicom_files:
        ai = AIInfo(model_name="unknown", modality_handled="XRAY", slices_reviewed=1, not_for_medical_use=True)
        study = StudyInfo()
        return _audit(localize_response(InterpretationResponse(
            exam_type="UNKNOWN",
            status="REVIEW_REQUIRED",
            findings=[],
            critical_alert=False,
            summary=build_summary([], output_language),
            study=study,
            ai=ai,
            warnings=["No DICOM files found in uploaded zip."],
            disclaimer=settings.disclaimer_text,
        ), output_language), clinical_indication)

    metadata = extract_dicom_metadata(str(dicom_dir))
    classification = classify_exam_type(
        modality=metadata.get("modality"),
        study_description=metadata.get("study_description"),
        series_description=metadata.get("series_description"),
        protocol_name=metadata.get("protocol_name"),
        body_part_examined=metadata.get("body_part_examined"),
    )
    exam_type = classification.exam_type
    detected_view = classification.view
    view_position = (metadata.get("view_position") or "").strip().upper()
    if view_position in {"PA", "AP"}:
        detected_view = view_position
    study_uid = metadata.get("study_instance_uid")
    warnings: list[str] = []

    expected_view_count = _expected_view_count(metadata.get("study_description"))
    actual_count = 1  # MVP: only first file processed
    missing_views_warning = None
    if expected_view_count and expected_view_count > actual_count:
        missing_views_warning = (
            f"Study description suggests {expected_view_count} views; "
            f"only {actual_count} image was processed. "
            "Additional views may reveal further findings."
        )
        warnings.append(missing_views_warning)

    mismatch_warning = _check_indication_mismatch(clinical_indication, exam_type)
    if mismatch_warning:
        logger.warning(mismatch_warning)
        warnings.append(mismatch_warning)

    if exam_type == "UNSUPPORTED_MODALITY":
        study = StudyInfo(
            study_instance_uid=study_uid,
            modality=metadata.get("modality"),
            body_part=(metadata.get("body_part_examined") or "").upper() or None,
            laterality=metadata.get("image_laterality"),
            view=detected_view,
            study_description=metadata.get("study_description"),
            series_description=metadata.get("series_description"),
            patient_age=metadata.get("patient_age"),
            patient_sex=metadata.get("patient_sex"),
            image_quality=None,
        )
        ai = AIInfo(model_name="unknown", modality_handled="XRAY", slices_reviewed=1, not_for_medical_use=True)
        return _audit(localize_response(InterpretationResponse(
            exam_type="UNSUPPORTED_MODALITY",
            status="UNSUPPORTED_MODALITY",
            findings=[],
            critical_alert=False,
            summary="Unsupported modality for this service. Radiologist review required.",
            study=study,
            ai=ai,
            warnings=[*warnings, "Only CR/DX X-ray modality is supported."],
            disclaimer=settings.disclaimer_text,
        ), output_language), clinical_indication)

    if not exam_type.startswith(SUPPORTED_EXAMS):
        study = StudyInfo(
            study_instance_uid=study_uid,
            modality=metadata.get("modality"),
            body_part=(metadata.get("body_part_examined") or "").upper() or None,
            laterality=metadata.get("image_laterality"),
            view=detected_view,
            study_description=metadata.get("study_description"),
            series_description=metadata.get("series_description"),
            patient_age=metadata.get("patient_age"),
            patient_sex=metadata.get("patient_sex"),
            image_quality=None,
        )
        ai = AIInfo(model_name="unknown", modality_handled="XRAY", slices_reviewed=1, not_for_medical_use=True)
        return _audit(localize_response(InterpretationResponse(
            exam_type=exam_type,
            status="REVIEW_REQUIRED",
            findings=[],
            critical_alert=False,
            summary=build_summary([], output_language),
            study=study,
            ai=ai,
            warnings=[*warnings, "Unsupported exam type for X-ray MVP interpretation."],
            disclaimer=settings.disclaimer_text,
        ), output_language), clinical_indication)

    if skip_image_model and not exam_type.startswith("XR_CHEST"):
        study = StudyInfo(
            study_instance_uid=study_uid,
            modality=metadata.get("modality"),
            body_part=(metadata.get("body_part_examined") or "").upper() or None,
            laterality=metadata.get("image_laterality"),
            view=detected_view,
            study_description=metadata.get("study_description"),
            series_description=metadata.get("series_description"),
            patient_age=metadata.get("patient_age"),
            patient_sex=metadata.get("patient_sex"),
            image_quality=None,
        )
        return _build_review_required_response(
            exam_type=exam_type,
            summary=(
                "Image interpretation was skipped because the configured local model does not support image input. "
                "Radiologist review required."
            ),
            warnings=[*warnings, skip_reason],
            output_language=output_language,
            settings=settings,
            clinical_indication=clinical_indication,
            study=study,
            model_name=selected_vision_model,
        )

    try:
        image_path = workdir / "xray.png"
        _dicom_to_png(dicom_files[0], image_path)
        available_views = _extract_available_views(dicom_files)
        metadata["available_views"] = available_views
        metadata["images_reviewed_count"] = 1
        metadata["detected_view"] = detected_view
        if exam_type.startswith("XR_CHEST"):
            # Chest: always use the purpose-built local CNN (accurate + free).
            findings, model_outputs, model_meta = run_xray_model(str(image_path), exam_type)
        elif _should_use_gpt(settings) and selected_vision_model:
            # Non-chest: no local CNN, fall back to the configured vision model
            # (Ollama or OpenAI, per OPENAI_BASE_URL / VISION_MODEL).
            from .gpt_xray_model import run_gpt_xray_model

            findings, _gpt_output, model_meta = run_gpt_xray_model(
                image_path=str(image_path),
                exam_type=exam_type,
                output_language=output_language,
                openai_api_key=(settings.openai_api_key or "").strip(),
                openai_base_url=settings.openai_base_url,
                openai_model=selected_vision_model,
                vision_image_url_as_string=settings.vision_image_url_as_string,
                openai_timeout=settings.openai_timeout,
                study_description=metadata.get("study_description"),
                series_description=metadata.get("series_description"),
                laterality=metadata.get("image_laterality"),
                view=classification.view,
            )
            model_outputs = {}
        else:
            raise RuntimeError(
                "No local model available for this body part; configure OPENAI_API_KEY to enable full X-ray coverage."
            )
    except Exception as e:
        reason = str(e) or e.__class__.__name__
        if reason == (
            "No local model available for this body part; configure OPENAI_API_KEY to enable full X-ray coverage."
        ):
            study = StudyInfo(
                study_instance_uid=study_uid,
                modality=metadata.get("modality"),
                body_part=(metadata.get("body_part_examined") or "").upper() or None,
                laterality=metadata.get("image_laterality"),
                view=detected_view,
                study_description=metadata.get("study_description"),
                series_description=metadata.get("series_description"),
                patient_age=metadata.get("patient_age"),
                patient_sex=metadata.get("patient_sex"),
                image_quality=None,
            )
            ai = AIInfo(model_name="unknown", modality_handled="XRAY", slices_reviewed=1, not_for_medical_use=True)
            return _audit(localize_response(InterpretationResponse(
                exam_type=exam_type,
                status="REVIEW_REQUIRED",
                findings=[],
                critical_alert=False,
                summary=build_summary([], output_language),
                study=study,
                ai=ai,
                warnings=[*warnings, reason],
                disclaimer=settings.disclaimer_text,
            ), output_language), clinical_indication)
        summary = "X-ray interpretation model inference failed. Radiologist review required."
        study = StudyInfo(
            study_instance_uid=study_uid,
            modality=metadata.get("modality"),
            body_part=(metadata.get("body_part_examined") or "").upper() or None,
            laterality=metadata.get("image_laterality"),
            view=detected_view,
            study_description=metadata.get("study_description"),
            series_description=metadata.get("series_description"),
            patient_age=metadata.get("patient_age"),
            patient_sex=metadata.get("patient_sex"),
            image_quality=None,
        )
        return _build_review_required_response(
            exam_type=exam_type,
            summary=summary,
            warnings=[*warnings, reason],
            output_language=output_language,
            settings=settings,
            clinical_indication=clinical_indication,
            study=study,
            model_name=selected_vision_model,
        )

    # Keep any pre-model warnings (e.g., clinical indication mismatch, missing views).
    expected_views = _expected_views_from_study_description(metadata.get("study_description"))
    images_reviewed_count = 1
    available_views = _extract_available_views(dicom_files)

    raw_model_view = str(model_meta.get("view_detected", "UNKNOWN") or "UNKNOWN").upper()
    final_view = detected_view or (raw_model_view if raw_model_view not in {"", "UNKNOWN"} else None)
    view_warning: str | None = None
    view_reconciliation: str | None = None

    if detected_view in {"PA", "AP"} and raw_model_view in {"PA", "AP"} and raw_model_view != detected_view:
        view_warning = (
            "Model view detection disagreed with DICOM metadata; metadata suggests PA."
            if detected_view == "PA"
            else "Model view detection disagreed with DICOM metadata; metadata suggests AP."
        )
        view_reconciliation = "metadata_preferred"
        warnings.append(view_warning)

    missing_views_warning: str | None = None
    single_frontal_only = images_reviewed_count == 1 and ("LATERAL" not in available_views)
    if single_frontal_only and exam_type.startswith("XR_CHEST"):
        warnings.append("Single frontal image reviewed; lateral view not available.")

    image_quality = str(model_meta.get("image_quality", "") or "").upper()
    if image_quality in {"LIMITED", "UNREADABLE"}:
        warnings.append("Image quality limitations reported by model; interpret findings cautiously.")

    findings, incidental_findings = _postprocess_xr_findings(
        findings=findings,
        exam_type=exam_type,
        final_view=final_view,
        single_frontal_only=single_frontal_only,
    )

    dicom_laterality = metadata.get("image_laterality")
    body_part_upper = (metadata.get("body_part_examined") or "").upper()

    if dicom_laterality is not None:
        # DICOM tag is authoritative — always use it
        final_laterality = dicom_laterality
    elif body_part_upper in BILATERAL_BODY_PARTS:
        # Bilateral study — never infer laterality from image
        final_laterality = None
    else:
        # Unilateral study, no DICOM tag — use model's image reading
        gpt_lat = model_meta.get("laterality_from_image")
        if gpt_lat in {"L", "R"}:
            final_laterality = "LEFT" if gpt_lat == "L" else "RIGHT"
        else:
            final_laterality = None

    study = StudyInfo(
        study_instance_uid=study_uid,
        modality=metadata.get("modality"),
        body_part=(metadata.get("body_part_examined") or "").upper() or None,
        laterality=final_laterality,
        view=final_view,
        study_description=metadata.get("study_description"),
        series_description=metadata.get("series_description"),
        patient_age=metadata.get("patient_age"),
        patient_sex=metadata.get("patient_sex"),
        image_quality=model_meta.get("image_quality"),
    )
    ai = AIInfo(
        model_name=str(model_meta.get("name") or selected_vision_model or "unknown"),
        modality_handled="XRAY",
        slices_reviewed=1,
        not_for_medical_use=True,
    )
    return _audit(localize_response(InterpretationResponse(
        exam_type=exam_type,
        status="COMPLETED",
        findings=findings,
        incidental_or_off_target_findings=incidental_findings,
        critical_alert=has_critical(findings),
        summary=build_summary(findings, output_language),
        study=study,
        ai=ai,
        warnings=warnings,
        disclaimer=settings.disclaimer_text,
    ), output_language), clinical_indication)
