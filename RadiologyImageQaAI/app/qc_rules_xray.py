from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .models import ExamType, IssueType, MissingRegion, QCStatus
from .protocol_classifier import classify_exam_type
from .report_generator import generate_explanation, localize_disclaimer, localize_text
from .config import get_settings


def _norm(text: str | None) -> str:
    return (text or "").strip().lower()


def _is_two_view_chest(study_description: str | None) -> bool:
    t = _norm(study_description)
    return any(
        k in t
        for k in [
            "2 views",
            "two views",
            "pa and lateral",
            "pa & lateral",
            "chest 2v",
            "chest 2 v",
            "chest 2-view",
            "chest 2 view",
        ]
    )


def _classify_view_position(vp: str | None) -> str | None:
    if not vp:
        return None
    t = vp.strip().upper()
    if t in {"PA", "AP"}:
        return t
    if t in {"LATERAL", "LAT"}:
        return "LATERAL"
    return t


def _basic_exposure_warning(pixel_array: np.ndarray) -> tuple[bool, dict[str, float]]:
    """
    Very simple heuristic exposure check:
      - mean too low -> too dark
      - mean too high -> too bright
      - std too low -> very low contrast
    Returns (is_warning, metrics)
    """
    arr = pixel_array.astype(np.float32)
    if arr.ndim > 2:
        # If multi-frame or RGB, collapse to luminance-ish mean.
        arr = arr.mean(axis=tuple(range(2, arr.ndim)))

    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return False, {}

    mean = float(np.mean(finite))
    std = float(np.std(finite))

    # Derive dynamic range from dtype when possible, else fall back to percentiles.
    if np.issubdtype(pixel_array.dtype, np.integer):
        info = np.iinfo(pixel_array.dtype)
        max_val = float(info.max)
        min_val = float(info.min)
    else:
        min_val = float(np.percentile(finite, 1))
        max_val = float(np.percentile(finite, 99))

    rng = max(1.0, max_val - min_val)
    mean_norm = (mean - min_val) / rng
    std_norm = std / rng

    is_bad_mean = mean_norm < 0.08 or mean_norm > 0.92
    is_low_contrast = std_norm < 0.03
    return bool(is_bad_mean or is_low_contrast), {"mean_norm": mean_norm, "std_norm": std_norm}


def evaluate_xray_qc(
    metadata: dict[str, Any],
    dicom_files: list[Path],
    output_language: str = "el",
) -> dict[str, Any]:
    """
    X-ray chest QC (metadata + simple pixel heuristics only).
    NOT diagnostic. Image-quality-only checks.
    """
    settings = get_settings()

    study_uid = str(metadata.get("study_instance_uid") or "UNKNOWN")
    study_description = metadata.get("study_description")
    body_part_examined = (metadata.get("body_part_examined") or "").strip().upper() or None
    modality = metadata.get("modality")
    series_description = metadata.get("series_description")
    protocol_name = metadata.get("protocol_name")
    view_position = metadata.get("view_position")

    exam_type = classify_exam_type(
        modality=modality,
        study_description=study_description,
        series_description=series_description,
        protocol_name=protocol_name,
        body_part_examined=body_part_examined,
        view_position=view_position,
    )

    details: dict[str, Any] = {"view_positions": [], "num_images": len(dicom_files)}

    if not dicom_files:
        qc_result = {
            "study_instance_uid": study_uid,
            "exam_type": exam_type,
            "qc_status": QCStatus.FAIL,
            "issue_type": IssueType.NO_IMAGES,
            "missing_region": None,
            "required_landmark_not_seen": None,
            "confidence": 0.9,
            "recommended_action": localize_text(
                "No DICOM images found. Verify the study upload and retry.",
                output_language,
            ),
            "human_review_required": True,
            "explanation": "",
            "disclaimer": localize_disclaimer(settings.disclaimer_text, output_language),
            "details": details,
        }
        qc_result["explanation"] = generate_explanation(
            qc_result,
            style="technologist_alert",
            settings=settings,
            output_language=output_language,
        )
        return qc_result

    # Read per-image ViewPosition and BodyPartExamined for completeness checks.
    try:
        import pydicom  # type: ignore
    except Exception as e:
        qc_result = {
            "study_instance_uid": study_uid,
            "exam_type": exam_type,
            "qc_status": QCStatus.REVIEW_REQUIRED,
            "issue_type": IssueType.MISSING_METADATA,
            "missing_region": None,
            "required_landmark_not_seen": None,
            "confidence": 0.0,
            "recommended_action": localize_text(
                "Verify DICOM metadata (pydicom not available in this runtime).",
                output_language,
            ),
            "human_review_required": True,
            "explanation": "",
            "disclaimer": localize_disclaimer(settings.disclaimer_text, output_language),
            "details": {**details, "error": str(e)},
        }
        qc_result["explanation"] = generate_explanation(
            qc_result,
            style="technologist_alert",
            settings=settings,
            output_language=output_language,
        )
        return qc_result

    view_positions: list[str | None] = []
    any_missing_view_position = False
    any_non_chest = False

    for fp in dicom_files:
        try:
            ds = pydicom.dcmread(str(fp), stop_before_pixels=True, force=True)
            vp = _classify_view_position(getattr(ds, "ViewPosition", None))
            view_positions.append(vp)
            if not vp:
                any_missing_view_position = True
            bp = str(getattr(ds, "BodyPartExamined", "") or "").strip().upper()
            if bp and bp != "CHEST":
                any_non_chest = True
        except Exception:
            view_positions.append(None)
            any_missing_view_position = True

    details["view_positions"] = [vp for vp in view_positions if vp]

    # Rule 2: ViewPosition presence
    if any_missing_view_position:
        qc_result = {
            "study_instance_uid": study_uid,
            "exam_type": exam_type,
            "qc_status": QCStatus.REVIEW_REQUIRED,
            "issue_type": IssueType.MISSING_METADATA,
            "missing_region": None,
            "required_landmark_not_seen": None,
            "confidence": 0.6,
            "recommended_action": localize_text(
                "Verify DICOM metadata (ViewPosition missing).",
                output_language,
            ),
            "human_review_required": True,
            "explanation": "",
            "disclaimer": localize_disclaimer(settings.disclaimer_text, output_language),
            "details": details,
        }
        qc_result["explanation"] = generate_explanation(
            qc_result,
            style="technologist_alert",
            settings=settings,
            output_language=output_language,
        )
        return qc_result

    # Rule 3: BodyPartExamined check
    if body_part_examined and body_part_examined != "CHEST":
        qc_result = {
            "study_instance_uid": study_uid,
            "exam_type": ExamType.XRAY_UNKNOWN,
            "qc_status": QCStatus.REVIEW_REQUIRED,
            "issue_type": IssueType.WRONG_BODY_PART,
            "missing_region": None,
            "required_landmark_not_seen": None,
            "confidence": 0.8,
            "recommended_action": localize_text(
                "Verify BodyPartExamined and route for human review.",
                output_language,
            ),
            "human_review_required": True,
            "explanation": "",
            "disclaimer": localize_disclaimer(settings.disclaimer_text, output_language),
            "details": details,
        }
        qc_result["explanation"] = generate_explanation(
            qc_result,
            style="technologist_alert",
            settings=settings,
            output_language=output_language,
        )
        return qc_result

    if any_non_chest:
        qc_result = {
            "study_instance_uid": study_uid,
            "exam_type": ExamType.XRAY_UNKNOWN,
            "qc_status": QCStatus.REVIEW_REQUIRED,
            "issue_type": IssueType.WRONG_BODY_PART,
            "missing_region": None,
            "required_landmark_not_seen": None,
            "confidence": 0.7,
            "recommended_action": localize_text(
                "Verify BodyPartExamined and route for human review.",
                output_language,
            ),
            "human_review_required": True,
            "explanation": "",
            "disclaimer": localize_disclaimer(settings.disclaimer_text, output_language),
            "details": details,
        }
        qc_result["explanation"] = generate_explanation(
            qc_result,
            style="technologist_alert",
            settings=settings,
            output_language=output_language,
        )
        return qc_result

    # Rule 1: View completeness (2 views)
    if _is_two_view_chest(study_description):
        has_pa_ap = any(v in {"PA", "AP"} for v in view_positions if v)
        has_lateral = any(v == "LATERAL" for v in view_positions if v)
        if not has_lateral:
            qc_result = {
                "study_instance_uid": study_uid,
                "exam_type": exam_type,
                "qc_status": QCStatus.FAIL,
                "issue_type": IssueType.MISSING_VIEW,
                "missing_region": MissingRegion.LATERAL_VIEW,
                "required_landmark_not_seen": None,
                "confidence": 0.85,
                "recommended_action": localize_text("Repeat lateral chest X-ray.", output_language),
                "human_review_required": True,
                "explanation": "",
                "disclaimer": localize_disclaimer(settings.disclaimer_text, output_language),
                "details": details,
            }
            qc_result["explanation"] = generate_explanation(
                qc_result,
                style="technologist_alert",
                settings=settings,
                output_language=output_language,
            )
            return qc_result
        if not has_pa_ap:
            qc_result = {
                "study_instance_uid": study_uid,
                "exam_type": exam_type,
                "qc_status": QCStatus.FAIL,
                "issue_type": IssueType.MISSING_VIEW,
                "missing_region": None,
                "required_landmark_not_seen": None,
                "confidence": 0.85,
                "recommended_action": localize_text(
                    "Repeat PA/AP chest X-ray (2-view study requires PA/AP and lateral).",
                    output_language,
                ),
                "human_review_required": True,
                "explanation": "",
                "disclaimer": localize_disclaimer(settings.disclaimer_text, output_language),
                "details": details,
            }
            qc_result["explanation"] = generate_explanation(
                qc_result,
                style="technologist_alert",
                settings=settings,
                output_language=output_language,
            )
            return qc_result

    # Rule 5: Basic exposure heuristic (warning only)
    exposure_warning = False
    exposure_metrics: dict[str, float] = {}
    exposure_error: str | None = None
    try:
        ds0 = pydicom.dcmread(str(dicom_files[0]), force=True)
        arr = ds0.pixel_array  # type: ignore[attr-defined]
        exposure_warning, exposure_metrics = _basic_exposure_warning(arr)
    except Exception as e:
        exposure_error = str(e)

    if exposure_metrics:
        details["exposure"] = exposure_metrics
    if exposure_error:
        details["exposure_error"] = exposure_error

    # Rule 6: Portable AP note
    notes: list[str] = []
    if any(v == "AP" for v in view_positions if v):
        notes.append(localize_text("Portable AP chest X-ray may have limited quality.", output_language))
    if notes:
        details["notes"] = "; ".join(notes)

    if exposure_warning:
        qc_result = {
            "study_instance_uid": study_uid,
            "exam_type": exam_type,
            "qc_status": QCStatus.WARNING,
            "issue_type": IssueType.POOR_EXPOSURE,
            "missing_region": None,
            "required_landmark_not_seen": None,
            "confidence": 0.8,
            "recommended_action": localize_text(
                "Review exposure/contrast; consider repeat image if clinically indicated.",
                output_language,
            ),
            "human_review_required": True,
            "explanation": "",
            "disclaimer": localize_disclaimer(settings.disclaimer_text, output_language),
            "details": details,
        }
        qc_result["explanation"] = generate_explanation(
            qc_result,
            style="technologist_alert",
            settings=settings,
            output_language=output_language,
        )
        return qc_result

    qc_result = {
        "study_instance_uid": study_uid,
        "exam_type": exam_type,
        "qc_status": QCStatus.PASS,
        "issue_type": IssueType.NO_ISSUE,
        "missing_region": None,
        "required_landmark_not_seen": None,
        "confidence": 0.8,
        "recommended_action": localize_text("No action required.", output_language),
        "human_review_required": False,
        "explanation": "",
        "disclaimer": localize_disclaimer(settings.disclaimer_text, output_language),
        "details": details,
    }
    qc_result["explanation"] = generate_explanation(
        qc_result,
        style="technologist_alert",
        settings=settings,
        output_language=output_language,
    )
    return qc_result
