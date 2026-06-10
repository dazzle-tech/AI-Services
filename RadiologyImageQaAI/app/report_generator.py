from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict

from .config import Settings
from .models import QCStatus

_SUPPORTED_OUTPUT_LANGUAGES = {"el", "en", "ar"}

_GENERIC_TRANSLATIONS = {
    "el": {
        "Research/MVP only. Not for clinical use without validation and regulatory approval.": (
            "Μόνο για ερευνητική/MVP χρήση. Δεν προορίζεται για κλινική χρήση χωρίς επικύρωση και κανονιστική έγκριση."
        ),
        "No action required.": "Δεν απαιτείται ενέργεια.",
        "No DICOM images found. Verify the study upload and retry.": (
            "Δεν βρέθηκαν εικόνες DICOM. Επαληθεύστε τη μεταφόρτωση της μελέτης και δοκιμάστε ξανά."
        ),
        "Verify DICOM metadata (pydicom not available in this runtime).": (
            "Επαληθεύστε τα μεταδεδομένα DICOM (το pydicom δεν είναι διαθέσιμο σε αυτό το περιβάλλον)."
        ),
        "Verify DICOM metadata (ViewPosition missing).": (
            "Επαληθεύστε τα μεταδεδομένα DICOM (λείπει το ViewPosition)."
        ),
        "Verify BodyPartExamined and route for human review.": (
            "Επαληθεύστε το BodyPartExamined και προωθήστε τη μελέτη για ανθρώπινο έλεγχο."
        ),
        "Repeat lateral chest X-ray.": "Επαναλάβετε την πλάγια ακτινογραφία θώρακος.",
        "Repeat PA/AP chest X-ray (2-view study requires PA/AP and lateral).": (
            "Επαναλάβετε την PA/AP ακτινογραφία θώρακος (η μελέτη 2 λήψεων απαιτεί PA/AP και πλάγια λήψη)."
        ),
        "Review exposure/contrast; consider repeat image if clinically indicated.": (
            "Ελέγξτε την έκθεση/αντίθεση και εξετάστε το ενδεχόμενο επανάληψης της εικόνας, αν κρίνεται κλινικά απαραίτητο."
        ),
        "Verify the uploaded file is a valid zipped CT DICOM study and retry.": (
            "Επαληθεύστε ότι το μεταφορτωμένο αρχείο είναι έγκυρη συμπιεσμένη μελέτη CT DICOM και δοκιμάστε ξανά."
        ),
        "X-ray study detected. Use /api/v1/qc/xray/dicom instead.": (
            "Ανιχνεύθηκε μελέτη ακτινογραφίας. Χρησιμοποιήστε αντ' αυτού το /api/v1/qc/xray/dicom."
        ),
        "CT study could not be classified into a supported protocol. Route for human review.": (
            "Η μελέτη CT δεν μπόρεσε να ταξινομηθεί σε υποστηριζόμενο πρωτόκολλο. Προωθήστε τη για ανθρώπινο έλεγχο."
        ),
        "DICOM conversion failed; route for human review or retry with a valid CT series.": (
            "Η μετατροπή DICOM απέτυχε. Προωθήστε τη μελέτη για ανθρώπινο έλεγχο ή δοκιμάστε ξανά με έγκυρη σειρά CT."
        ),
        "Automatic coverage QC is unavailable (segmentation missing/failed). Route for human review or install TotalSegmentator.": (
            "Ο αυτόματος έλεγχος κάλυψης δεν είναι διαθέσιμος (λείπει ή απέτυχε η τμηματοποίηση). Προωθήστε τη μελέτη για ανθρώπινο έλεγχο ή εγκαταστήστε το TotalSegmentator."
        ),
        "Verify the uploaded file is a valid zipped X-ray DICOM study and retry.": (
            "Επαληθεύστε ότι το μεταφορτωμένο αρχείο είναι έγκυρη συμπιεσμένη μελέτη DICOM ακτινογραφίας και δοκιμάστε ξανά."
        ),
        "Non X-ray study detected. Use /api/v1/qc/ct/dicom for CT studies.": (
            "Ανιχνεύθηκε μη ακτινογραφική μελέτη. Χρησιμοποιήστε το /api/v1/qc/ct/dicom για μελέτες CT."
        ),
        "Portable AP chest X-ray may have limited quality.": (
            "Η φορητή AP ακτινογραφία θώρακος ενδέχεται να έχει περιορισμένη ποιότητα."
        ),
    },
    "ar": {
        "Research/MVP only. Not for clinical use without validation and regulatory approval.": (
            "للاستخدام البحثي/النسخة الأولية فقط. غير مخصص للاستخدام السريري دون تحقق واعتماد تنظيمي."
        ),
        "No action required.": "لا يلزم اتخاذ أي إجراء.",
        "No DICOM images found. Verify the study upload and retry.": (
            "لم يتم العثور على صور DICOM. تحقّق من رفع الدراسة وأعد المحاولة."
        ),
        "Verify DICOM metadata (pydicom not available in this runtime).": (
            "تحقّق من بيانات DICOM الوصفية (مكتبة pydicom غير متاحة في هذا التشغيل)."
        ),
        "Verify DICOM metadata (ViewPosition missing).": (
            "تحقّق من بيانات DICOM الوصفية (حقل ViewPosition مفقود)."
        ),
        "Verify BodyPartExamined and route for human review.": (
            "تحقّق من BodyPartExamined وحوّل الدراسة للمراجعة البشرية."
        ),
        "Repeat lateral chest X-ray.": "أعد تصوير الصدر بالوضعية الجانبية.",
        "Repeat PA/AP chest X-ray (2-view study requires PA/AP and lateral).": (
            "أعد تصوير الصدر بوضعية PA/AP (الدراسة ذات العرضين تتطلب PA/AP ووضعية جانبية)."
        ),
        "Review exposure/contrast; consider repeat image if clinically indicated.": (
            "راجع التعريض/التباين وفكّر بإعادة الصورة إذا وُجدت ضرورة سريرية."
        ),
        "Verify the uploaded file is a valid zipped CT DICOM study and retry.": (
            "تحقّق من أن الملف المرفوع دراسة CT DICOM مضغوطة صالحة وأعد المحاولة."
        ),
        "X-ray study detected. Use /api/v1/qc/xray/dicom instead.": (
            "تم اكتشاف دراسة أشعة سينية. استخدم /api/v1/qc/xray/dicom بدلاً من ذلك."
        ),
        "CT study could not be classified into a supported protocol. Route for human review.": (
            "تعذّر تصنيف دراسة CT ضمن بروتوكول مدعوم. حوّلها للمراجعة البشرية."
        ),
        "DICOM conversion failed; route for human review or retry with a valid CT series.": (
            "فشل تحويل DICOM. حوّل الدراسة للمراجعة البشرية أو أعد المحاولة بسلسلة CT صالحة."
        ),
        "Automatic coverage QC is unavailable (segmentation missing/failed). Route for human review or install TotalSegmentator.": (
            "فحص التغطية الآلي غير متاح (التقسيم مفقود أو فشل). حوّل الدراسة للمراجعة البشرية أو ثبّت TotalSegmentator."
        ),
        "Verify the uploaded file is a valid zipped X-ray DICOM study and retry.": (
            "تحقّق من أن الملف المرفوع دراسة أشعة سينية DICOM مضغوطة صالحة وأعد المحاولة."
        ),
        "Non X-ray study detected. Use /api/v1/qc/ct/dicom for CT studies.": (
            "تم اكتشاف دراسة ليست أشعة سينية. استخدم /api/v1/qc/ct/dicom لدراسات CT."
        ),
        "Portable AP chest X-ray may have limited quality.": (
            "قد تكون جودة صورة الصدر المحمولة بوضعية AP محدودة."
        ),
    },
}


def normalize_output_language(output_language: str | None) -> str:
    language = (output_language or "el").strip().lower()
    return language if language in _SUPPORTED_OUTPUT_LANGUAGES else "el"


def localize_text(text: str | None, output_language: str = "el") -> str:
    value = str(text or "").strip()
    language = normalize_output_language(output_language)
    if not value or language == "en":
        return value
    return _GENERIC_TRANSLATIONS.get(language, {}).get(value, value)


def localize_disclaimer(disclaimer_text: str, output_language: str = "el") -> str:
    return localize_text(disclaimer_text, output_language)


def _enum_value(v: Any) -> Any:
    if isinstance(v, Enum):
        return v.value
    return v


def _template_explanation(qc_result: Dict[str, Any], style: str, output_language: str) -> str:
    status = _enum_value(qc_result.get("qc_status", QCStatus.REVIEW_REQUIRED))
    status = str(status)
    missing_region = _enum_value(qc_result.get("missing_region"))
    landmark = _enum_value(qc_result.get("required_landmark_not_seen"))
    recommended = localize_text(qc_result.get("recommended_action", ""), output_language)
    language = normalize_output_language(output_language)

    if language == "ar":
        if status == QCStatus.PASS.value:
            return "نجح فحص الجودة: تبدو التغطية التشريحية المطلوبة كافية. لا يلزم اتخاذ إجراء فوري."
        if status == QCStatus.WARNING.value:
            parts = [f"تحذير جودة: توجد ملاحظة محتملة تتعلق بالتغطية عند {landmark}."]
            if recommended:
                parts.append(f"الإجراء الموصى به: {recommended}")
            return " ".join(parts)
        if status == QCStatus.FAIL.value:
            parts = [f"فشل فحص الجودة: تبدو التغطية التشريحية غير مكتملة في {missing_region}."]
            if landmark:
                parts.append(f"المعلم المفقود أو غير المؤكد: {landmark}.")
            if recommended:
                parts.append(f"الإجراء الموصى به: {recommended}")
            return " ".join(parts)
        parts = ["مراجعة الجودة مطلوبة: كان فحص الجودة الآلي غير متاح أو غير حاسم، لذا يلزم التدخل البشري."]
        if recommended:
            parts.append(f"الإجراء الموصى به: {recommended}")
        return " ".join(parts)

    if language == "el":
        if status == QCStatus.PASS.value:
            return "ΕΠΙΤΥΧΙΑ QC: Η απαιτούμενη ανατομική κάλυψη φαίνεται επαρκής. Δεν απαιτείται άμεση ενέργεια."
        if status == QCStatus.WARNING.value:
            parts = [f"ΠΡΟΕΙΔΟΠΟΙΗΣΗ QC: Πιθανό ζήτημα κάλυψης που σχετίζεται με {landmark}."]
            if recommended:
                parts.append(f"Προτεινόμενη ενέργεια: {recommended}")
            return " ".join(parts)
        if status == QCStatus.FAIL.value:
            parts = [f"ΑΠΟΤΥΧΙΑ QC: Η ανατομική κάλυψη φαίνεται ελλιπής στην περιοχή {missing_region}."]
            if landmark:
                parts.append(f"Απόν ή αβέβαιο ανατομικό σημείο: {landmark}.")
            if recommended:
                parts.append(f"Προτεινόμενη ενέργεια: {recommended}")
            return " ".join(parts)
        parts = ["ΑΠΑΙΤΕΙΤΑΙ ΑΝΘΡΩΠΙΝΟΣ ΕΛΕΓΧΟΣ QC: Ο αυτόματος έλεγχος δεν ήταν διαθέσιμος ή ήταν ασαφής."]
        if recommended:
            parts.append(f"Προτεινόμενη ενέργεια: {recommended}")
        return " ".join(parts)

    if status == QCStatus.PASS.value:
        return "QC PASS: Required anatomical coverage appears adequate. No immediate action required."

    if status == QCStatus.WARNING.value:
        parts = [f"QC WARNING: Potential coverage issue related to {landmark}."]
        if recommended:
            parts.append(f"Recommended action: {recommended}")
        return " ".join(parts)
    if status == QCStatus.FAIL.value:
        parts = [f"QC FAIL: Anatomical coverage appears incomplete in {missing_region}."]
        if landmark:
            parts.append(f"Missing/uncertain landmark: {landmark}.")
        if recommended:
            parts.append(f"Recommended action: {recommended}")
        return " ".join(parts)

    parts = ["QC REVIEW REQUIRED: Automatic QC was unavailable or inconclusive; human review is required."]
    if recommended:
        parts.append(f"Recommended action: {recommended}")
    return " ".join(parts)


def generate_explanation(
    qc_result: Dict[str, Any],
    *,
    style: str,
    settings: Settings,
    output_language: str = "el",
) -> str:
    """
    Generates a human-readable QC explanation.
    This MUST NOT be diagnostic. Only technical/coverage QC.
    """
    return _template_explanation(qc_result, style, output_language)


def generate_explanation_with_openai(
    qc_result: Dict[str, Any],
    *,
    style: str,
    settings: Settings,
    output_language: str = "el",
) -> str:
    """
    Optional: Use OpenAI Responses API for phrasing only (never for coverage detection).
    This function is intentionally isolated and safe-fails to deterministic templates.
    """
    if not settings.openai_enabled or not settings.openai_api_key:
        return _template_explanation(qc_result, style, output_language)

    if settings.deidentify_before_gpt:
        qc_payload = {
            k: qc_result.get(k)
            for k in [
                "exam_type",
                "qc_status",
                "issue_type",
                "missing_region",
                "required_landmark_not_seen",
                "confidence",
                "recommended_action",
                "human_review_required",
            ]
        }
    else:
        qc_payload = qc_result

    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return _template_explanation(qc_result, style, output_language)

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = (
        "You are generating a radiology technical quality-control alert for a CT study.\n"
        "Do NOT diagnose. Do NOT suggest clinical interpretations.\n"
        "Explain the QC result clearly for a CT technologist. Keep it concise.\n"
        f"Style: {style}\n"
        f"Requested output language: {normalize_output_language(output_language)}\n"
        "Write only the explanation text in the requested language, but keep machine-readable codes unchanged.\n"
        f"Structured QC JSON:\n{json.dumps(qc_payload, indent=2)}\n"
    )

    try:
        resp = client.responses.create(
            model=settings.openai_model,
            input=prompt,
        )
        text = getattr(resp, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        return _template_explanation(qc_result, style, output_language)
    except Exception:
        return _template_explanation(qc_result, style, output_language)
