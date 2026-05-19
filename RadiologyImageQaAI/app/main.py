from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Dict

from fastapi import Depends, FastAPI, File, Form, UploadFile

from .config import Settings, get_settings
from .dicom_utils import extract_dicom_metadata, extract_zip, find_dicom_files, read_metadata
from .models import (
    ExamType,
    ExplainRequest,
    ExplainResponse,
    IssueType,
    QCResult,
    QCStatus,
)
from .protocol_classifier import classify_exam_type
from .qc_rules import run_qc_for_exam_type
from .report_generator import generate_explanation, generate_explanation_with_openai
from .segmentation import detect_landmarks_from_masks, run_totalsegmentator
from .storage import temp_workdir


app = FastAPI(title="Radiology QC AI", version="0.1.0")
@app.get("/health")
def health(settings: Settings = Depends(get_settings)) -> Dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


def _finalize_explanation(
    qc_result: Dict[str, Any],
    *,
    use_gpt_report: bool,
    settings: Settings,
    style: str = "technologist_alert",
) -> str:
    if use_gpt_report:
        return generate_explanation_with_openai(qc_result, style=style, settings=settings)
    return generate_explanation(qc_result, style=style, settings=settings)


def _filter_detection_notes(notes: str, exam_type: ExamType) -> str:
    """
    Keep only protocol-relevant heuristic notes for the given exam type.
    Notes are semicolon-separated strings produced by `detect_landmarks_from_masks`.
    """
    if not notes:
        return ""

    items = [n.strip() for n in notes.split(";") if n.strip()]
    if not items:
        return ""

    def keep(note: str) -> bool:
        t = note.lower()

        is_head_note = ("brain" in t) or ("skull" in t) or ("vertex" in t)
        is_pubic_note = ("pubic" in t) or ("pelvis" in t) or ("hip" in t) or ("sacrum" in t)

        # Rule-based exclusions first.
        if exam_type != ExamType.CT_HEAD and is_head_note:
            return False
        if exam_type not in (ExamType.CT_ABDOMEN_PELVIS, ExamType.CT_CHEST_ABDOMEN_PELVIS) and is_pubic_note:
            return False

        if exam_type == ExamType.CT_CHEST:
            return "lung" in t or "apices" in t or "bases" in t
        if exam_type == ExamType.CT_HEAD:
            return is_head_note
        if exam_type == ExamType.CT_ABDOMEN:
            return ("lung" in t) or ("diaphragm" in t) or ("liver" in t) or ("kidney" in t)
        if exam_type == ExamType.CT_ABDOMEN_PELVIS:
            return (
                ("lung" in t)
                or ("diaphragm" in t)
                or ("bladder" in t)
                or is_pubic_note
            )
        if exam_type == ExamType.CT_CHEST_ABDOMEN_PELVIS:
            return ("lung" in t) or is_pubic_note

        return False

    filtered = [n for n in items if keep(n)]
    return "; ".join(filtered)


def _convert_dicom_to_nifti(dicom_root: Path, out_dir: Path) -> Path:
    """
    Best-effort conversion using dicom2nifti.
    Returns path to a .nii/.nii.gz file.
    """
    try:
        import dicom2nifti  # type: ignore
    except Exception as e:
        raise RuntimeError("dicom2nifti is not available.") from e

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        dicom2nifti.convert_directory(str(dicom_root), str(out_dir), compression=True, reorient=True)
    except Exception as e:
        raise RuntimeError(f"DICOM to NIfTI conversion failed: {e}") from e

    nifti_candidates = list(out_dir.rglob("*.nii.gz")) + list(out_dir.rglob("*.nii"))
    if not nifti_candidates:
        raise RuntimeError("No NIfTI output produced by dicom2nifti.")
    return nifti_candidates[0]


async def _extract_and_classify(
    *,
    workdir: Path,
    file: UploadFile,
) -> tuple[
    Path,
    list[Path],
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    ExamType,
]:
    zip_path = workdir / "upload.zip"
    content = await file.read()
    zip_path.write_bytes(content)

    extract_dir = workdir / "dicom"
    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        extract_zip(zip_path, extract_dir)
    except zipfile.BadZipFile:
        # Support single-file upload: treat the uploaded payload as a single DICOM file.
        # (Common Postman usage is to upload one .dcm, not a zipped study.)
        single_name = Path(getattr(file, "filename", "") or "single.dcm").name
        if not single_name:
            single_name = "single.dcm"
        # Ensure the saved file is discoverable by `find_dicom_files` (expects .dcm or no suffix).
        if Path(single_name).suffix and Path(single_name).suffix.lower() != ".dcm":
            stem = Path(single_name).stem or "single"
            single_name = f"{stem}.dcm"
        (extract_dir / single_name).write_bytes(content)

    dicom_files = find_dicom_files(extract_dir)
    if not dicom_files:
        raise RuntimeError("No DICOM files detected after extraction.")

    meta_dict = extract_dicom_metadata(str(extract_dir))
    if any(v is not None for v in meta_dict.values()):
        modality = meta_dict.get("modality")
        study_description = meta_dict.get("study_description")
        series_description = meta_dict.get("series_description")
        protocol_name = meta_dict.get("protocol_name")
        body_part_examined = meta_dict.get("body_part_examined")
        view_position = meta_dict.get("view_position")
        study_uid = meta_dict.get("study_instance_uid") or "UNKNOWN"
    else:
        meta = read_metadata(dicom_files)
        modality = meta.modality
        study_description = meta.study_description
        series_description = meta.series_description
        protocol_name = meta.protocol_name
        body_part_examined = meta.body_part_examined
        view_position = meta.view_position
        study_uid = meta.study_instance_uid or "UNKNOWN"

    exam_type = classify_exam_type(
        modality=modality,
        study_description=study_description,
        series_description=series_description,
        protocol_name=protocol_name,
        body_part_examined=body_part_examined,
        view_position=view_position,
    )

    return (
        extract_dir,
        dicom_files,
        study_uid,
        modality,
        study_description,
        series_description,
        protocol_name,
        body_part_examined,
        view_position,
        exam_type,
    )


def _qc_review_required(
    *,
    study_uid: str,
    exam_type: ExamType,
    issue_type: IssueType,
    recommended_action: str,
    settings: Settings,
    details: dict[str, Any],
) -> QCResult:
    qc_dict: Dict[str, Any] = {
        "study_instance_uid": study_uid,
        "exam_type": exam_type,
        "qc_status": QCStatus.REVIEW_REQUIRED,
        "issue_type": issue_type,
        "missing_region": None,
        "required_landmark_not_seen": None,
        "confidence": 0.0,
        "recommended_action": recommended_action,
        "human_review_required": True,
        "explanation": _finalize_explanation(
            {
                "qc_status": QCStatus.REVIEW_REQUIRED.value,
                "recommended_action": recommended_action,
            },
            use_gpt_report=False,
            settings=settings,
        ),
        "disclaimer": settings.disclaimer_text,
        "details": details,
    }
    return QCResult(**qc_dict)


@app.post("/api/v1/qc/ct/dicom", response_model=QCResult)
async def qc_ct_dicom_upload(
    file: UploadFile = File(...),
    use_gpt_report: bool = Form(False),
    settings: Settings = Depends(get_settings),
) -> QCResult:
    with temp_workdir() as workdir:
        try:
            (
                extract_dir,
                dicom_files,
                study_uid,
                modality,
                study_description,
                series_description,
                protocol_name,
                body_part_examined,
                view_position,
                exam_type,
            ) = await _extract_and_classify(workdir=workdir, file=file)
        except Exception as e:
            return _qc_review_required(
                study_uid="UNKNOWN",
                exam_type=ExamType.UNKNOWN,
                issue_type=IssueType.PIPELINE_ERROR,
                recommended_action="Verify the uploaded file is a valid zipped CT DICOM study and retry.",
                settings=settings,
                details={"stage": "extract_zip_or_metadata", "error": str(e)},
            )

        if str(exam_type.value).startswith("XR_") or exam_type == ExamType.XRAY_UNKNOWN or exam_type == ExamType.XRAY:
            return _qc_review_required(
                study_uid=study_uid,
                exam_type=exam_type,
                issue_type=IssueType.UNSUPPORTED_PROTOCOL,
                recommended_action="X-ray study detected. Use /api/v1/qc/xray/dicom instead.",
                settings=settings,
                details={
                    "stage": "classify_protocol",
                    "modality": modality,
                    "study_description": study_description,
                    "series_description": series_description,
                    "protocol_name": protocol_name,
                    "body_part_examined": body_part_examined,
                    "view_position": view_position,
                },
            )

        supported_ct = {
            ExamType.CT_CHEST,
            ExamType.CT_HEAD,
            ExamType.CT_ABDOMEN,
            ExamType.CT_ABDOMEN_PELVIS,
            ExamType.CT_CHEST_ABDOMEN_PELVIS,
        }
        if exam_type not in supported_ct:
            return _qc_review_required(
                study_uid=study_uid,
                exam_type=exam_type,
                issue_type=IssueType.UNSUPPORTED_PROTOCOL,
                recommended_action="CT study could not be classified into a supported protocol. Route for human review.",
                settings=settings,
                details={
                    "stage": "classify_protocol",
                    "modality": modality,
                    "study_description": study_description,
                    "series_description": series_description,
                    "protocol_name": protocol_name,
                    "body_part_examined": body_part_examined,
                    "view_position": view_position,
                },
            )

        nifti_dir = workdir / "nifti"
        seg_dir = workdir / "seg"
        seg_dir.mkdir(parents=True, exist_ok=True)

        try:
            nifti_path = _convert_dicom_to_nifti(extract_dir, nifti_dir)
        except Exception as e:
            return _qc_review_required(
                study_uid=study_uid,
                exam_type=exam_type,
                issue_type=IssueType.PIPELINE_ERROR,
                recommended_action="DICOM conversion failed; route for human review or retry with a valid CT series.",
                settings=settings,
                details={"stage": "dicom2nifti", "error": str(e)},
            )

        try:
            run_totalsegmentator(str(nifti_path), str(seg_dir))
        except Exception as e:
            return _qc_review_required(
                study_uid=study_uid,
                exam_type=exam_type,
                issue_type=IssueType.REVIEW_REQUIRED,
                recommended_action="Automatic coverage QC is unavailable (segmentation missing/failed). Route for human review or install TotalSegmentator.",
                settings=settings,
                details={"stage": "totalsegmentator", "error": str(e)},
            )

        detection = detect_landmarks_from_masks(seg_dir)
        rule = run_qc_for_exam_type(
            exam_type,
            landmarks=detection.landmarks,
            settings=settings,
            derived_from_segmentation=True,
        )

        qc_dict: Dict[str, Any] = {
            "study_instance_uid": study_uid,
            "exam_type": exam_type,
            "qc_status": rule.qc_status,
            "issue_type": IssueType.INCOMPLETE_ANATOMICAL_COVERAGE
            if rule.qc_status in (QCStatus.WARNING, QCStatus.FAIL)
            else IssueType.NO_ISSUE,
            "missing_region": rule.missing_region,
            "required_landmark_not_seen": rule.required_landmark_not_seen,
            "confidence": min(rule.confidence, detection.confidence),
            "recommended_action": rule.recommended_action,
            "human_review_required": rule.human_review_required,
            "explanation": "",
            "disclaimer": settings.disclaimer_text,
            "details": {
                "source": "totalsegmentator_masks",
                "notes": _filter_detection_notes(detection.notes, exam_type),
            },
        }
        qc_dict["explanation"] = _finalize_explanation(
            qc_dict, use_gpt_report=use_gpt_report, settings=settings
        )
        return QCResult(**qc_dict)


@app.post("/api/v1/qc/xray/dicom", response_model=QCResult)
async def qc_xray_dicom_upload(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> QCResult:
    with temp_workdir() as workdir:
        try:
            (
                extract_dir,
                dicom_files,
                study_uid,
                modality,
                study_description,
                series_description,
                protocol_name,
                body_part_examined,
                view_position,
                exam_type,
            ) = await _extract_and_classify(workdir=workdir, file=file)
        except Exception as e:
            return _qc_review_required(
                study_uid="UNKNOWN",
                exam_type=ExamType.UNKNOWN,
                issue_type=IssueType.PIPELINE_ERROR,
                recommended_action="Verify the uploaded file is a valid zipped X-ray DICOM study and retry.",
                settings=settings,
                details={"stage": "extract_zip_or_metadata", "error": str(e)},
            )

        supported_xray = {
            ExamType.XR_CHEST,
            ExamType.XR_CHEST_PA,
            ExamType.XR_CHEST_AP,
            ExamType.XR_CHEST_LATERAL,
            ExamType.XRAY_UNKNOWN,
            ExamType.XRAY,
        }
        if exam_type not in supported_xray:
            return _qc_review_required(
                study_uid=study_uid,
                exam_type=exam_type,
                issue_type=IssueType.UNSUPPORTED_PROTOCOL,
                recommended_action="Non X-ray study detected. Use /api/v1/qc/ct/dicom for CT studies.",
                settings=settings,
                details={
                    "stage": "classify_protocol",
                    "modality": modality,
                    "study_description": study_description,
                    "series_description": series_description,
                    "protocol_name": protocol_name,
                    "body_part_examined": body_part_examined,
                    "view_position": view_position,
                },
            )

        from .qc_rules_xray import evaluate_xray_qc

        qc_payload = evaluate_xray_qc(
            metadata={
                "modality": modality,
                "study_description": study_description,
                "series_description": series_description,
                "protocol_name": protocol_name,
                "body_part_examined": body_part_examined,
                "study_instance_uid": study_uid,
                "view_position": view_position,
            },
            dicom_files=dicom_files,
        )
        qc_payload.setdefault("disclaimer", settings.disclaimer_text)
        return QCResult(**qc_payload)


@app.post("/api/v1/report/explain", response_model=ExplainResponse)
def explain_report(
    payload: ExplainRequest,
    settings: Settings = Depends(get_settings),
) -> ExplainResponse:
    explanation = generate_explanation(payload.qc_result, style=payload.style, settings=settings)
    return ExplainResponse(explanation=explanation)
