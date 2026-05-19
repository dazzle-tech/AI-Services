from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any
import re

import numpy as np
import pydicom  # type: ignore
from PIL import Image
from pydicom.misc import is_dicom  # type: ignore

from ..config import Settings
from ..dicom_utils import extract_dicom_metadata, find_dicom_files
from ..protocol_classifier import SUPPORTED_EXAMS, ExamClassification, classify_exam_type
from .models import AIInfo, Finding, InterpretationResponse, StudyInfo
from .xray_model import STRONG_THRESHOLD, WEAK_THRESHOLD, run_xray_model
from ..audit import log_interpretation


_VIEW_WORD_RE = re.compile(r"(^|\s)(pa|ap)(\s|$)", re.IGNORECASE)
_TWO_VIEWS_RE = re.compile(r"(\b2\b|two)\s*view", re.IGNORECASE)

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

def build_summary(findings: list[Finding]) -> str:
    if not findings:
        return (
            "No AI candidate acute finding identified above configured thresholds. "
            "Radiologist review required."
        )

    has_standard = any((f.confidence or 0.0) >= STRONG_THRESHOLD for f in findings)
    if not has_standard:
        return "Low-confidence AI candidate finding detected. Radiologist review required."

    if len(findings) == 1:
        return "One AI candidate finding detected. Radiologist review required."
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


def build_image_response(
    *,
    upload_input_path: Path,
    workdir: Path,
    clinical_indication: str | None,
    settings: Settings,
    exam_type: str = "XR_CHEST",
) -> InterpretationResponse:
    image_path = workdir / "xray_input.png"
    warnings: list[str] = []
    mismatch_warning = _check_indication_mismatch(clinical_indication, exam_type)
    if mismatch_warning:
        import logging

        logging.getLogger(__name__).warning(mismatch_warning)
        warnings.append(mismatch_warning)

    try:
        _load_upload_to_png(upload_input_path, image_path)
    except Exception as e:
        reason = str(e) or e.__class__.__name__
        study = StudyInfo(image_quality="UNREADABLE")
        ai = AIInfo(model_name="unknown", modality_handled="XRAY", slices_reviewed=1, not_for_medical_use=True)
        return _audit(InterpretationResponse(
            exam_type=exam_type,
            status="REVIEW_REQUIRED",
            critical_alert=False,
            summary="Unsupported or unreadable image file. Radiologist review required.",
            findings=[],
            study=study,
            ai=ai,
            warnings=[*warnings, reason],
            disclaimer=settings.disclaimer_text,
        ), clinical_indication)

    try:
        if _should_use_gpt(settings):
            from .gpt_xray_model import run_gpt_xray_model

            findings, _gpt_output, model_meta = run_gpt_xray_model(
                image_path=str(image_path),
                exam_type=exam_type,
                openai_api_key=(settings.openai_api_key or "").strip(),
                openai_model=settings.openai_model,
                openai_timeout=settings.openai_timeout_seconds,
                study_description=None,
                series_description=None,
                laterality=None,
                view=None,
            )
            model_outputs = {}
        else:
            if exam_type.startswith("XR_CHEST"):
                findings, model_outputs, model_meta = run_xray_model(str(image_path), exam_type)
            else:
                raise RuntimeError(
                    "No local model available for this body part; configure OPENAI_API_KEY to enable full X-ray coverage."
                )
    except Exception as e:
        reason = str(e) or e.__class__.__name__
        study = StudyInfo(image_quality="UNREADABLE")
        ai = AIInfo(model_name="unknown", modality_handled="XRAY", slices_reviewed=1, not_for_medical_use=True)
        if reason == "No local model available for this body part; configure OPENAI_API_KEY to enable full X-ray coverage.":
            return _audit(InterpretationResponse(
                exam_type=exam_type,
                status="REVIEW_REQUIRED",
                findings=[],
                critical_alert=False,
                summary=build_summary([]),
                study=study,
                ai=ai,
                warnings=[*warnings, reason],
                disclaimer=settings.disclaimer_text,
            ), clinical_indication)
        return _audit(InterpretationResponse(
            exam_type=exam_type,
            status="REVIEW_REQUIRED",
            critical_alert=False,
            summary="X-ray interpretation model inference failed. Radiologist review required.",
            findings=[],
            study=study,
            ai=ai,
            warnings=[*warnings, reason],
            disclaimer=settings.disclaimer_text,
        ), clinical_indication)

    study = StudyInfo(image_quality=str(model_meta.get("image_quality") or "UNKNOWN"))
    model_lat = _normalize_model_laterality(model_meta.get("laterality_from_image"))
    if model_lat:
        study.laterality = model_lat
    ai = AIInfo(
        model_name=str(model_meta.get("name", "unknown") or "unknown"),
        modality_handled="XRAY",
        slices_reviewed=1,
        not_for_medical_use=True,
    )
    return _audit(InterpretationResponse(
        exam_type=exam_type,
        status="COMPLETED",
        findings=findings,
        critical_alert=has_critical(findings),
        summary=build_summary(findings),
        study=study,
        ai=ai,
        warnings=warnings,
        disclaimer=settings.disclaimer_text,
    ), clinical_indication)


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
    settings: Settings,
) -> InterpretationResponse:
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
            settings=settings,
            exam_type="XR_CHEST",
        )

    dicom_dir = workdir / "dicom"
    dicom_files = _load_upload_to_dicom_dir(upload_input_path, dicom_dir)
    import logging

    _logger = logging.getLogger(__name__)
    if len(dicom_files) > 1:
        _logger.warning(
            "Zip contains %d DICOM files; only the first will be used for interpretation (MVP behaviour).",
            len(dicom_files),
        )
    if not dicom_files:
        ai = AIInfo(model_name="unknown", modality_handled="XRAY", slices_reviewed=1, not_for_medical_use=True)
        study = StudyInfo()
        return _audit(InterpretationResponse(
            exam_type="UNKNOWN",
            status="REVIEW_REQUIRED",
            findings=[],
            critical_alert=False,
            summary=build_summary([]),
            study=study,
            ai=ai,
            warnings=["No DICOM files found in uploaded zip."],
            disclaimer=settings.disclaimer_text,
        ), clinical_indication)

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
        _logger.warning(mismatch_warning)
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
        return _audit(InterpretationResponse(
            exam_type="UNSUPPORTED_MODALITY",
            status="UNSUPPORTED_MODALITY",
            findings=[],
            critical_alert=False,
            summary="Unsupported modality for this service. Radiologist review required.",
            study=study,
            ai=ai,
            warnings=[*warnings, "Only CR/DX X-ray modality is supported."],
            disclaimer=settings.disclaimer_text,
        ), clinical_indication)

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
        return _audit(InterpretationResponse(
            exam_type=exam_type,
            status="REVIEW_REQUIRED",
            findings=[],
            critical_alert=False,
            summary=build_summary([]),
            study=study,
            ai=ai,
            warnings=[*warnings, "Unsupported exam type for X-ray MVP interpretation."],
            disclaimer=settings.disclaimer_text,
        ), clinical_indication)

    try:
        image_path = workdir / "xray.png"
        _dicom_to_png(dicom_files[0], image_path)
        available_views = _extract_available_views(dicom_files)
        metadata["available_views"] = available_views
        metadata["images_reviewed_count"] = 1
        metadata["detected_view"] = detected_view
        if _should_use_gpt(settings):
            from .gpt_xray_model import run_gpt_xray_model

            findings, _gpt_output, model_meta = run_gpt_xray_model(
                image_path=str(image_path),
                exam_type=exam_type,
                openai_api_key=(settings.openai_api_key or "").strip(),
                openai_model=settings.openai_model,
                openai_timeout=settings.openai_timeout_seconds,
                study_description=metadata.get("study_description"),
                series_description=metadata.get("series_description"),
                laterality=metadata.get("image_laterality"),
                view=classification.view,
            )
            model_outputs = {}
        else:
            if exam_type.startswith("XR_CHEST"):
                findings, model_outputs, model_meta = run_xray_model(str(image_path), exam_type)
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
            return _audit(InterpretationResponse(
                exam_type=exam_type,
                status="REVIEW_REQUIRED",
                findings=[],
                critical_alert=False,
                summary=build_summary([]),
                study=study,
                ai=ai,
                warnings=[*warnings, reason],
                disclaimer=settings.disclaimer_text,
            ), clinical_indication)
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
        ai = AIInfo(model_name="unknown", modality_handled="XRAY", slices_reviewed=1, not_for_medical_use=True)
        return _audit(InterpretationResponse(
            exam_type=exam_type,
            status="REVIEW_REQUIRED",
            findings=[],
            critical_alert=False,
            summary=summary,
            study=study,
            ai=ai,
            warnings=[*warnings, reason],
            disclaimer=settings.disclaimer_text,
        ), clinical_indication)

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

    # Apply chest-specific safety post-processing
    adjusted_findings: list[Any] = []
    incidental_low_conf: list[dict[str, Any]] = []
    for f in findings:
        if not exam_type.startswith("XR_CHEST"):
            adjusted_findings.append(f)
            continue

        code = (getattr(f, "finding_code", "") or "").upper()
        location = getattr(f, "location", None)
        confidence = float(getattr(f, "confidence", 0.0) or 0.0)
        finding_text = getattr(f, "finding_text", "")

        # Avoid lobe-specific localization on single frontal views.
        if single_frontal_only and isinstance(location, str) and "lobe" in location.lower():
            new_loc, changed = _zone_location_from_lobe(location)
            if changed:
                location = new_loc
                confidence = min(confidence, 0.55)

        # Cardiomegaly: reduce overconfidence and adjust wording based on view.
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
            adjusted_findings.append(
                f.model_copy(
                    update={
                        "location": location,
                        "confidence": confidence,
                        "finding_text": finding_text,
                        "priority": priority,
                    }
                )
            )
            continue

        # Opacity/consolidation: stricter + avoid high confidence on single frontal.
        if code in {"PULMONARY_OPACITY", "LUNG_OPACITY", "CONSOLIDATION", "PNEUMONIA", "INFILTRATION"}:
            if single_frontal_only:
                confidence = min(confidence, 0.45 if confidence < 0.70 else 0.55)
            # Omit very low confidence
            if confidence < 0.35:
                incidental_low_conf.append(
                    {
                        "finding_code": code,
                        "location": location,
                        "confidence": confidence,
                        "reason": "Below configured confidence threshold for reporting.",
                    }
                )
                continue

            if single_frontal_only and code in {"PULMONARY_OPACITY", "LUNG_OPACITY"} and confidence <= 0.55:
                code = "LOWER_ZONE_OPACITY"
                if isinstance(location, str) and location.strip():
                    loc_text = location.strip()
                else:
                    loc_text = "lower lung zone"
                location = loc_text
                finding_text = (
                    "Questionable mild basilar opacity or vascular crowding. Radiologist review required."
                )

        adjusted_findings.append(
            f.model_copy(
                update={
                    "finding_code": code,
                    "location": location,
                    "confidence": confidence,
                    "finding_text": finding_text,
                }
            )
        )

    findings = adjusted_findings

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
        model_name=str(model_meta.get("name", "unknown") or "unknown"),
        modality_handled="XRAY",
        slices_reviewed=1,
        not_for_medical_use=True,
    )
    return _audit(InterpretationResponse(
        exam_type=exam_type,
        status="COMPLETED",
        findings=findings,
        critical_alert=has_critical(findings),
        summary=build_summary(findings),
        study=study,
        ai=ai,
        warnings=warnings,
        disclaimer=settings.disclaimer_text,
    ), clinical_indication)
