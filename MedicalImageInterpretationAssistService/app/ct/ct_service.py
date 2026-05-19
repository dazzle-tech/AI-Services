from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from typing import Any

import pydicom
from pydicom.misc import is_dicom

from ..config import Settings
from ..audit import log_interpretation
from ..interpretation.models import AIInfo, Finding, InterpretationResponse, StudyInfo
from ..interpretation.interpretation_service import build_summary, has_critical
from ..storage import temp_workdir
from .ct_dicom_utils import (
    build_series_index,
    dicom_slice_to_png,
    extract_ct_metadata,
    find_dicom_files,
    safe_extract_zip,
    select_representative_slices,
)
from .gpt_ct_model import run_gpt_ct_model

logger = logging.getLogger(__name__)

ACCEPTED_CT_MODALITIES = {"CT"}
MAX_SLICES = 6  # GPT-4o image limit per call; 6 well-spaced slices covers most studies

CT_SERIES_CLASSES = {
    "ABDOMEN_SOFT_TISSUE",
    "CHEST_LUNG_WINDOW",
    "CHEST_SOFT_TISSUE",
    "LUNG_BASES_FROM_ABDOMEN",
    "UNKNOWN_CT",
}

_CHEST_ONLY_FINDING_CODES = {
    "PULMONARY_NODULE",
    "MEDIASTINAL_LYMPHADENOPATHY",
    "PNEUMOTHORAX",
    "PLEURAL_EFFUSION",
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


def _norm(text: str | None) -> str:
    return (text or "").lower().replace("\\", " ").replace("/", " ").replace("-", " ").strip()


def _classify_ct_series(meta: dict[str, Any], requested_exam_type: str) -> str:
    combined = " ".join(
        [
            _norm(meta.get("study_description")),
            _norm(meta.get("series_description")),
            _norm(meta.get("body_part_examined")),
            _norm(meta.get("protocol_name")),
            _norm(meta.get("convolution_kernel")),
            _norm(meta.get("image_type")),
        ]
    )

    wc = meta.get("window_center")
    ww = meta.get("window_width")

    lung_keywords = any(k in combined for k in ["lung", "chest", "thorax", "pulmon", "pleura", "mediastin"])
    abd_keywords = any(k in combined for k in ["abdomen", "abdominal", "abd", "pelvis", "kub", "kidney ureter"])

    lung_window = False
    try:
        lung_window = (wc is not None and float(wc) < -300.0) and (ww is not None and float(ww) > 1000.0)
    except Exception:
        lung_window = False

    kernel = _norm(meta.get("convolution_kernel"))
    sharp_kernel = any(
        k in kernel for k in ["lung", "sharp", "bone", "b70", "b80", "fc50", "br57", "br64", "bl57", "ul"]
    )

    soft_tissue_window = False
    try:
        soft_tissue_window = (wc is not None and -150.0 <= float(wc) <= 150.0) and (
            ww is not None and 200.0 <= float(ww) <= 800.0
        )
    except Exception:
        soft_tissue_window = False

    if lung_keywords or lung_window or sharp_kernel:
        if requested_exam_type == "CT_ABDOMEN":
            return "LUNG_BASES_FROM_ABDOMEN"
        return "CHEST_LUNG_WINDOW"

    if requested_exam_type == "CT_ABDOMEN":
        if abd_keywords and (not lung_keywords) and (not lung_window) and soft_tissue_window:
            return "ABDOMEN_SOFT_TISSUE"
        return "UNKNOWN_CT"

    if lung_keywords and soft_tissue_window:
        return "CHEST_SOFT_TISSUE"

    return "UNKNOWN_CT"


def _select_best_series(
    series_index: list[dict[str, Any]],
    requested_exam_type: str,
) -> tuple[str, dict[str, Any], list[Path]]:
    classified: list[tuple[str, dict[str, Any], list[Path]]] = []
    for entry in series_index:
        meta = entry.get("meta") or {}
        files = entry.get("files") or []
        klass = _classify_ct_series(meta, requested_exam_type)
        classified.append((klass, meta, files))

    if requested_exam_type == "CT_ABDOMEN":
        abdomen = [c for c in classified if c[0] == "ABDOMEN_SOFT_TISSUE" and c[2]]
        if abdomen:
            return abdomen[0]
        non_lung = [
            c for c in classified if c[0] not in {"CHEST_LUNG_WINDOW", "LUNG_BASES_FROM_ABDOMEN"} and c[2]
        ]
        if non_lung:
            return non_lung[0]
        lung = [c for c in classified if c[0] in {"CHEST_LUNG_WINDOW", "LUNG_BASES_FROM_ABDOMEN"} and c[2]]
        if lung:
            return lung[0]

    for c in classified:
        if c[2]:
            return c

    return "UNKNOWN_CT", {}, []


def build_ct_response(
    *,
    upload_input_path: Path,
    workdir: Path,
    clinical_indication: str | None,
    settings: Settings,
    max_slices: int = MAX_SLICES,
) -> InterpretationResponse:
    warnings: list[str] = []
    # Require OpenAI key — CT has no local model fallback
    if not settings.openai_api_key:
        study = StudyInfo(modality="CT", body_part=None, view="AXIAL")
        ai = AIInfo(model_name="unknown", modality_handled="CT", slices_reviewed=0, not_for_medical_use=True)
        return _audit(InterpretationResponse(
            exam_type="CT_UNKNOWN",
            status="REVIEW_REQUIRED",
            findings=[],
            critical_alert=False,
            summary="CT interpretation requires OPENAI_API_KEY to be configured. Radiologist review required.",
            study=study,
            ai=ai,
            warnings=["OPENAI_API_KEY not set."],
            disclaimer=settings.disclaimer_text,
        ), clinical_indication)

    # Unpack zip or single DICOM
    dicom_dir = workdir / "dicom"
    dicom_dir.mkdir(parents=True, exist_ok=True)

    if zipfile.is_zipfile(upload_input_path):
        try:
            safe_extract_zip(upload_input_path, dicom_dir)
        except ValueError as e:
            study = StudyInfo(modality="CT", body_part=None, view="AXIAL")
            ai = AIInfo(model_name="unknown", modality_handled="CT", slices_reviewed=0, not_for_medical_use=True)
            return _audit(InterpretationResponse(
                exam_type="CT_UNKNOWN",
                status="REVIEW_REQUIRED",
                findings=[],
                critical_alert=False,
                summary="Zip file rejected for security reasons. Radiologist review required.",
                study=study,
                ai=ai,
                warnings=[str(e)],
                disclaimer=settings.disclaimer_text,
            ), clinical_indication)
    elif is_dicom(str(upload_input_path)):
        single = dicom_dir / "upload.dcm"
        single.write_bytes(upload_input_path.read_bytes())
    else:
        study = StudyInfo(modality="CT", body_part=None, view="AXIAL")
        ai = AIInfo(model_name="unknown", modality_handled="CT", slices_reviewed=0, not_for_medical_use=True)
        return _audit(InterpretationResponse(
            exam_type="CT_UNKNOWN",
            status="REVIEW_REQUIRED",
            findings=[],
            critical_alert=False,
            summary="Uploaded file is not a DICOM file or zip archive. Radiologist review required.",
            study=study,
            ai=ai,
            warnings=["Not DICOM or zip."],
            disclaimer=settings.disclaimer_text,
        ), clinical_indication)

    dicom_files = find_dicom_files(dicom_dir)
    if not dicom_files:
        study = StudyInfo(modality="CT", body_part=None, view="AXIAL")
        ai = AIInfo(model_name="unknown", modality_handled="CT", slices_reviewed=0, not_for_medical_use=True)
        return _audit(InterpretationResponse(
            exam_type="CT_UNKNOWN",
            status="REVIEW_REQUIRED",
            findings=[],
            critical_alert=False,
            summary="No DICOM files found in upload. Radiologist review required.",
            study=study,
            ai=ai,
            warnings=["No DICOM files found."],
            disclaimer=settings.disclaimer_text,
        ), clinical_indication)

    metadata = extract_ct_metadata(dicom_files)
    metadata["slice_count"] = len(dicom_files)
    study_uid = metadata.get("study_instance_uid")

    requested_body_part = (metadata.get("body_part_examined") or "UNKNOWN").upper()
    requested_exam_type = f"CT_{requested_body_part}"

    # Validate modality
    modality = (metadata.get("modality") or "").strip().upper()
    if modality not in ACCEPTED_CT_MODALITIES:
        study = StudyInfo(
            study_instance_uid=study_uid,
            modality=modality,
            body_part=(metadata.get("body_part_examined") or "").upper() or None,
            view="AXIAL",
            study_description=metadata.get("study_description"),
            series_description=metadata.get("series_description"),
        )
        ai = AIInfo(model_name="unknown", modality_handled="CT", slices_reviewed=0, not_for_medical_use=True)
        return _audit(InterpretationResponse(
            exam_type="UNSUPPORTED_MODALITY",
            status="UNSUPPORTED_MODALITY",
            findings=[],
            critical_alert=False,
            summary=f"Modality '{modality}' is not supported by the CT endpoint. Only CT is accepted. Radiologist review required.",
            study=study,
            ai=ai,
            warnings=[f"Modality {modality} rejected by CT endpoint."],
            disclaimer=settings.disclaimer_text,
        ), clinical_indication)

    # Series selection + representative slices
    series_index = build_series_index(dicom_files)
    if not series_index:
        series_index = [{"meta": dict(metadata), "files": dicom_files}]
    selected_series_class, selected_series_meta, selected_series_files = _select_best_series(
        series_index,
        requested_exam_type,
    )

    selected = select_representative_slices(selected_series_files, max_slices=max_slices)
    slice_png_paths: list[str] = []
    slices_dir = workdir / "slices"
    slices_dir.mkdir(exist_ok=True)

    for i, dcm_path in enumerate(selected):
        png_path = slices_dir / f"slice_{i:03d}.png"
        try:
            dicom_slice_to_png(dcm_path, png_path)
            slice_png_paths.append(str(png_path))
        except Exception as e:
            logger.warning("Failed to convert slice %s: %s", dcm_path.name, e)
            continue

    if not slice_png_paths:
        study = StudyInfo(
            study_instance_uid=study_uid,
            modality="CT",
            body_part=(metadata.get("body_part_examined") or "").upper() or None,
            view="AXIAL",
            study_description=metadata.get("study_description"),
            series_description=metadata.get("series_description"),
        )
        ai = AIInfo(model_name="unknown", modality_handled="CT", slices_reviewed=0, not_for_medical_use=True)
        return _audit(InterpretationResponse(
            exam_type="CT_UNKNOWN",
            status="REVIEW_REQUIRED",
            findings=[],
            critical_alert=False,
            summary="No CT slices could be decoded from the uploaded DICOM. Radiologist review required.",
            study=study,
            ai=ai,
            warnings=["All slice conversions failed."],
            disclaimer=settings.disclaimer_text,
        ), clinical_indication)

    exam_type = requested_exam_type
    metadata["selected_series_meta"] = selected_series_meta
    metadata["selected_series_class"] = selected_series_class

    try:
        findings, gpt_output, model_meta = run_gpt_ct_model(
            slice_png_paths=slice_png_paths,
            exam_type=exam_type,
            metadata=metadata,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
            openai_timeout=settings.openai_timeout_seconds,
        )
    except Exception as e:
        logger.error("CT model inference failed: %s", e)
        study = StudyInfo(
            study_instance_uid=study_uid,
            modality="CT",
            body_part=(metadata.get("body_part_examined") or "").upper() or None,
            view="AXIAL",
            study_description=metadata.get("study_description"),
            series_description=metadata.get("series_description"),
        )
        ai = AIInfo(model_name="unknown", modality_handled="CT", slices_reviewed=0, not_for_medical_use=True)
        return _audit(InterpretationResponse(
            exam_type=exam_type,
            status="REVIEW_REQUIRED",
            findings=[],
            critical_alert=False,
            summary="CT interpretation model inference failed. Radiologist review required.",
            study=study,
            ai=ai,
            warnings=[str(e)],
            disclaimer=settings.disclaimer_text,
        ), clinical_indication)

    # Reconcile body part + suppress out-of-scope finding families for abdomen
    model_body_part = str(gpt_output.get("body_part", "UNKNOWN") or "UNKNOWN").upper()
    mismatch = False
    warnings: list[str] = []

    if requested_body_part == "ABDOMEN" and (
        selected_series_class in {"CHEST_LUNG_WINDOW", "LUNG_BASES_FROM_ABDOMEN"} or model_body_part == "CHEST"
    ):
        mismatch = True
        warnings.append(
            "Body part mismatch: study labeled ABDOMEN but selected series appears to be chest/lung-window or lung-bases; abdominal-organ interpretation is limited."
        )

    incidental: list[dict[str, Any]] = []
    final_findings: list[Finding] = findings
    if requested_body_part == "ABDOMEN":
        kept: list[Finding] = []
        for f in findings:
            if f.finding_code in _CHEST_ONLY_FINDING_CODES:
                incidental.append(f.model_dump())
            else:
                kept.append(f)
        final_findings = kept
        if incidental and mismatch:
            warnings.append(
                "Out-of-scope chest candidate findings suppressed from the main findings."
            )

    status = "COMPLETED"
    if mismatch:
        status = "REVIEW_REQUIRED"
        # Do not present routine abdomen interpretation when the selected series is out-of-scope.
        final_findings = []

    study = StudyInfo(
        study_instance_uid=study_uid,
        modality="CT",
        body_part=(metadata.get("body_part_examined") or "").upper() or None,
        laterality=None,
        view="AXIAL",
        study_description=metadata.get("study_description"),
        series_description=metadata.get("series_description"),
        image_quality=model_meta.get("image_quality"),
    )
    ai = AIInfo(
        model_name=str(model_meta.get("name", "unknown") or "unknown"),
        modality_handled="CT",
        slices_reviewed=len(slice_png_paths),
        not_for_medical_use=True,
    )

    if mismatch:
        warnings.append("Body part mismatch: selected series not appropriate for abdominal-organ interpretation.")
    if incidental:
        warnings.append("Out-of-scope chest candidate findings suppressed from main findings.")

    return _audit(InterpretationResponse(
        exam_type=exam_type,
        status=status,
        findings=final_findings,
        critical_alert=has_critical(final_findings),
        summary=build_summary(final_findings),
        study=study,
        ai=ai,
        warnings=warnings,
        disclaimer=settings.disclaimer_text,
    ), clinical_indication)
