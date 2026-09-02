from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import zipfile
from datetime import datetime
from io import BytesIO
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.responses import StreamingResponse
import pydicom
from pydantic import BaseModel
import uuid


ROOT = Path(__file__).resolve().parent
SAVED_DIR = ROOT / "saved"
SAVED_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger(__name__)

_DICOM_ORDER_MISMATCH_WARNING = (
    "WARNING: Uploaded DICOM StudyInstanceUID does not match the accession number in the order form. "
    "Radiologist notes may refer to a different study. Manual verification required before report finalisation."
)
_DICOM_ORDER_MISMATCH_SUBJECT_PREFIX = "[WARNING: DICOM/ORDER MISMATCH] "
_ACCESSION_TOKEN_PATTERN = re.compile(r"\bACC[-A-Z0-9_.]+\b", re.IGNORECASE)
_STUDY_UID_PATTERN = re.compile(r"\b\d+(?:\.\d+){3,}\b")

PACS_PROTOCOL = os.getenv("PACS_PROTOCOL", "dicomweb")

# DICOMweb settings (used if PACS_PROTOCOL == "dicomweb")
PACS_BASE_URL = os.getenv("PACS_BASE_URL")
PACS_AUTH_TOKEN = os.getenv("PACS_AUTH_TOKEN")
PACS_USERNAME = os.getenv("PACS_USERNAME")
PACS_PASSWORD = os.getenv("PACS_PASSWORD")

# DIMSE settings (used if PACS_PROTOCOL == "dimse")
PACS_HOST = os.getenv("PACS_HOST")
PACS_PORT = int(os.getenv("PACS_PORT", "104"))
PACS_AE_TITLE = os.getenv("PACS_AE_TITLE", "RADIOLOGY_WORKFLOW")
PACS_REMOTE_AE_TITLE = os.getenv("PACS_REMOTE_AE_TITLE", "PACS")
PACS_MOVE_DESTINATION_AE = os.getenv("PACS_MOVE_DESTINATION_AE")

# Shared PACS settings
PACS_TIMEOUT_SECONDS = float(os.getenv("PACS_TIMEOUT_SECONDS", "30"))
PACS_ENABLED = os.getenv("PACS_ENABLED", "false").lower() == "true"

# Sub-service base URLs. Default to localhost (the monolith / subprocess layout);
# override via env to point at the compose service containers.
_QC = os.getenv("QC_SERVICE_URL", "http://127.0.0.1:8016")
_INTERP = os.getenv("INTERP_SERVICE_URL", "http://127.0.0.1:8015")
_REPORT = os.getenv("REPORT_SERVICE_URL", "http://127.0.0.1:8024")
_AUTOFILL = os.getenv("AUTOFILL_SERVICE_URL", "http://127.0.0.1:8022")


HealthPath = Literal["/health", "/api/v1/health"]


@dataclass(frozen=True)
class ServiceDef:
    name: str
    cwd: Path
    port: int
    health_path: HealthPath
    startup_timeout_s: float = 30.0

    @property
    def health_url(self) -> str:
        # Use the env-configured base URL (compose service) when set, else localhost.
        base = {
            "RadiologyImageQaAI": _QC,
            "MedicalImageInterpretationAssistService": _INTERP,
            "RadiologyReportFilling": _REPORT,
            "MedicalImageTemplateAutofill": _AUTOFILL,
        }.get(self.name, f"http://127.0.0.1:{self.port}")
        return f"{base}{self.health_path}"


SERVICES: list[ServiceDef] = [
    ServiceDef(
        name="RadiologyImageQaAI",
        cwd=ROOT.parent / "RadiologyImageQaAI",
        port=8016,
        health_path="/health",
        startup_timeout_s=25.0,
    ),
    ServiceDef(
        name="MedicalImageInterpretationAssistService",
        cwd=ROOT.parent / "MedicalImageInterpretationAssistService",
        port=8015,
        health_path="/health",
        startup_timeout_s=35.0,
    ),
    ServiceDef(
        name="RadiologyReportFilling",
        cwd=ROOT.parent / "RadiologyReportFilling",
        port=8000,
        health_path="/api/v1/health",
        startup_timeout_s=35.0,
    ),
    ServiceDef(
        name="MedicalImageTemplateAutofill",
        cwd=ROOT.parent / "MedicalImageTemplateAutofill",
        port=8022,
        health_path="/health",
        startup_timeout_s=120.0,
    ),
]


def print_service_port_map() -> None:
    print("\n===== WORKFLOW SERVICES =====", flush=True)
    for service in SERVICES:
        print(
            f"{service.name}: port {service.port} ({service.health_url})",
            flush=True,
        )
    print("", flush=True)


def _popen_kwargs_for_windows() -> dict[str, Any]:
    if os.name != "nt":
        return {}

    creationflags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags |= subprocess.CREATE_NO_WINDOW

    return {"creationflags": creationflags}


SERVICE_PROCS: dict[str, subprocess.Popen[bytes]] = {}


async def check_health(url: str, timeout_s: float = 2.0) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            return True, resp.text
    except Exception as e:  # noqa: BLE001
        return False, str(e)


async def wait_for_health(url: str, deadline_s: float) -> tuple[bool, str]:
    """
    Poll health until success or deadline.
    """
    end = asyncio.get_event_loop().time() + deadline_s
    last_detail = "not checked"
    while asyncio.get_event_loop().time() < end:
        ok, detail = await check_health(url, timeout_s=2.5)
        last_detail = detail
        if ok:
            return True, detail
        await asyncio.sleep(1.0)
    return False, last_detail


async def ensure_services_running(start_missing: bool) -> dict[str, Any]:
    results: dict[str, Any] = {"services": []}
    for s in SERVICES:
        ok, detail = await check_health(s.health_url)
        started = False
        if (not ok) and start_missing:
            started = start_service(s)
            if started:
                ok, detail = await wait_for_health(s.health_url, deadline_s=s.startup_timeout_s)
        results["services"].append(
            {
                "name": s.name,
                "health_url": s.health_url,
                "running": ok,
                "detail": detail,
                "started": started,
            }
        )
    return results


def start_service(s: ServiceDef) -> bool:
    if not s.cwd.exists():
        return False

    existing = SERVICE_PROCS.get(s.name)
    if existing and existing.poll() is None:
        return True

    # Default: keep this launcher quiet. For debugging, set `SERVICE_STDIO=inherit`
    # and services will print to this process console.
    stdio_mode = (os.environ.get("SERVICE_STDIO") or "devnull").strip().lower()
    if stdio_mode == "inherit":
        stdout_target: Any = None
        stderr_target: Any = None
    else:
        stdout_target = subprocess.DEVNULL
        stderr_target = subprocess.DEVNULL

    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=str(s.cwd),
        stdout=stdout_target,
        stderr=stderr_target,
        **_popen_kwargs_for_windows(),
    )

    SERVICE_PROCS[s.name] = proc
    return True


def stop_service(name: str) -> bool:
    proc = SERVICE_PROCS.get(name)
    if not proc:
        return False

    if proc.poll() is not None:
        return True

    try:
        if os.name == "nt":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
        return True
    except Exception:  # noqa: BLE001
        return False


def stop_all_services() -> dict[str, Any]:
    return {"stopped": {name: stop_service(name) for name in list(SERVICE_PROCS.keys())}}


def qc_endpoint_for_modality(modality: str) -> str:
    if modality.upper() in {"CR", "DX"}:
        return f"{_QC}/api/v1/qc/xray/dicom"
    return f"{_QC}/api/v1/qc/ct/dicom"


def interpretation_endpoint_for_modality(modality: str) -> str:
    if modality.upper() in {"CR", "DX"}:
        return f"{_INTERP}/api/v1/radiology/xray-interpretation/dicom"
    return f"{_INTERP}/api/v1/radiology/ct-interpretation/dicom"


def _as_zip_bytes(filename: str, content: bytes) -> tuple[str, bytes]:
    """
    Services expect a single multipart `file` upload that is typically a ZIP.
    If a user uploads a single `.dcm`, wrap it into an in-memory zip.
    """
    lower = filename.lower()
    if lower.endswith(".zip"):
        return filename, content

    if not (lower.endswith(".dcm") or lower.endswith(".dicom")):
        raise ValueError("Only .zip or .dcm files are supported")

    base = Path(filename).name
    if not base.lower().endswith(".dcm"):
        base = f"{base}.dcm"

    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(base, content)
    return "dicom.zip", buf.getvalue()


def _normalize_dicom_scalar(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or None
    text = str(value).strip()
    return text or None


def _read_first_dicom_dataset(upload_name: str, dicom_bytes: bytes):
    """Read the first usable DICOM dataset from an uploaded DICOM or ZIP payload."""
    candidates: list[bytes] = []
    lower_name = upload_name.lower()
    if lower_name.endswith(".zip"):
        try:
            with zipfile.ZipFile(BytesIO(dicom_bytes)) as zf:
                for member in zf.namelist():
                    if member.endswith("/"):
                        continue
                    try:
                        candidates.append(zf.read(member))
                    except Exception:  # noqa: BLE001
                        continue
        except zipfile.BadZipFile:
            candidates = [dicom_bytes]
    else:
        candidates = [dicom_bytes]

    for blob in candidates:
        try:
            ds = pydicom.dcmread(BytesIO(blob), stop_before_pixels=True, force=True)
        except Exception:  # noqa: BLE001
            continue
        if any(
            getattr(ds, field, None) not in (None, "")
            for field in ("Modality", "StudyDate", "PatientName", "SOPClassUID")
        ):
            return ds
    return None


def _resolve_upload_metadata(
    upload_name: str,
    dicom_bytes: bytes,
    *,
    modality: str,
    study_date: str,
    patient_name: str,
    patient_sex: str,
    patient_age: str | None = None,
    pixel_spacing: Any = None,
    view_position: str | None = None,
) -> dict[str, Any]:
    """Prefer DICOM metadata when present; otherwise keep workflow/order values."""
    ds = _read_first_dicom_dataset(upload_name, dicom_bytes)

    dicom_modality = _normalize_dicom_scalar(getattr(ds, "Modality", None)) if ds is not None else None
    if dicom_modality:
        resolved_modality = str(dicom_modality)
    else:
        resolved_modality = modality
        logger.warning("Modality not found in DICOM; using order value: %s", modality)

    return {
        "modality": resolved_modality,
        "study_date": _normalize_dicom_scalar(getattr(ds, "StudyDate", None)) if ds is not None else None,
        "view_position": _normalize_dicom_scalar(getattr(ds, "ViewPosition", None)) if ds is not None else None,
        "patient_name": _normalize_dicom_scalar(getattr(ds, "PatientName", None)) if ds is not None else None,
        "patient_sex": _normalize_dicom_scalar(getattr(ds, "PatientSex", None)) if ds is not None else None,
        "patient_age": _normalize_dicom_scalar(getattr(ds, "PatientAge", None)) if ds is not None else None,
        "pixel_spacing": _normalize_dicom_scalar(getattr(ds, "PixelSpacing", None)) if ds is not None else None,
        "order_modality": modality,
        "order_study_date": study_date,
        "order_patient_name": patient_name,
        "order_patient_sex": patient_sex,
        "order_patient_age": patient_age,
        "order_pixel_spacing": pixel_spacing,
        "order_view_position": view_position,
    }


def _merged_upload_metadata(
    upload_name: str,
    dicom_bytes: bytes,
    *,
    modality: str,
    study_date: str,
    patient_name: str,
    patient_sex: str,
    patient_age: str | None = None,
    pixel_spacing: Any = None,
    view_position: str | None = None,
) -> dict[str, Any]:
    resolved = _resolve_upload_metadata(
        upload_name,
        dicom_bytes,
        modality=modality,
        study_date=study_date,
        patient_name=patient_name,
        patient_sex=patient_sex,
        patient_age=patient_age,
        pixel_spacing=pixel_spacing,
        view_position=view_position,
    )
    return {
        "modality": resolved.get("modality") or modality,
        "study_date": resolved.get("study_date") or study_date,
        "view_position": resolved.get("view_position") or view_position,
        "patient_name": resolved.get("patient_name") or patient_name,
        "patient_sex": resolved.get("patient_sex") or patient_sex,
        "patient_age": resolved.get("patient_age") or patient_age,
        "pixel_spacing": resolved.get("pixel_spacing") if resolved.get("pixel_spacing") is not None else pixel_spacing,
    }


def _infer_view_position_from_text(*values: Any) -> tuple[str | None, bool]:
    """Infer PA/AP/LATERAL from descriptive text when ViewPosition is absent."""
    text = " ".join(str(value or "") for value in values).upper()
    if not text.strip():
        return None, False
    if "PA" in text:
        return "PA", True
    if "AP" in text:
        return "AP", True
    if "LATERAL" in text or "LAT" in text:
        return "LATERAL", True
    return None, False


def _extract_parse_dicom_payload(upload_name: str, dicom_bytes: bytes) -> dict[str, Any]:
    """Extract upload metadata for the frontend prefill flow."""
    ds = _read_first_dicom_dataset(upload_name, dicom_bytes)
    if ds is None:
        raise ValueError("The uploaded file could not be parsed as a DICOM study.")

    requested_fields = {
        "PatientID": "patient_id",
        "PatientName": "patient_name",
        "PatientSex": "patient_sex",
        "PatientAge": "patient_age",
        "Modality": "modality",
        "StudyDate": "study_date",
        "BodyPartExamined": "body_part",
        "ViewPosition": "view_position",
        "AccessionNumber": "accession_number",
        "StudyInstanceUID": "study_instance_uid",
        "PixelSpacing": "pixel_spacing",
        "Manufacturer": "manufacturer",
        "InstitutionName": "institution_name",
    }

    response: dict[str, Any] = {}
    missing: list[str] = []
    for dicom_key, response_key in requested_fields.items():
        value = _normalize_dicom_scalar(getattr(ds, dicom_key, None))
        response[response_key] = value
        if value is None:
            missing.append(dicom_key)

    study_description = _normalize_dicom_scalar(getattr(ds, "StudyDescription", None))
    series_description = _normalize_dicom_scalar(getattr(ds, "SeriesDescription", None))
    exam_type = study_description or series_description or response.get("body_part")
    inferred_view_position, inferred = _infer_view_position_from_text(
        series_description,
        study_description,
        exam_type,
    )
    if response.get("view_position") is None and inferred_view_position:
        response["view_position"] = inferred_view_position

    response["exam_type"] = exam_type
    response["view_position_inferred"] = bool(inferred and inferred_view_position)
    response["missing"] = missing
    return response


def _normalized_identifier(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _extract_accession_tokens(text: str) -> set[str]:
    return {match.upper() for match in _ACCESSION_TOKEN_PATTERN.findall(text or "")}


def _extract_study_uids(text: str) -> set[str]:
    return {match.strip() for match in _STUDY_UID_PATTERN.findall(text or "")}


def _build_dicom_order_mismatch_context(
    parsed_dicom: dict[str, Any] | None,
    *,
    order_accession: str,
    radiologist_notes: str,
    order_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parsed = parsed_dicom if isinstance(parsed_dicom, dict) else {}
    order_meta = order_metadata if isinstance(order_metadata, dict) else {}

    uploaded_accession = _normalized_identifier(parsed.get("accession_number"))
    uploaded_study_uid = _normalized_identifier(parsed.get("study_instance_uid"))

    accession_candidates = _extract_accession_tokens(radiologist_notes)
    expected_accession = _normalized_identifier(order_accession) or _normalized_identifier(order_meta.get("AccessionNumber"))
    if expected_accession:
        accession_candidates.add(expected_accession.upper())

    study_uid_candidates = _extract_study_uids(radiologist_notes)
    expected_study_uid = _normalized_identifier(order_meta.get("StudyInstanceUID"))
    if expected_study_uid:
        study_uid_candidates.add(expected_study_uid)

    reasons: list[str] = []
    if uploaded_accession and accession_candidates and uploaded_accession.upper() not in accession_candidates:
        reasons.append(
            "Uploaded DICOM accession number does not match the accession number recorded in the order context."
        )
    if uploaded_study_uid and study_uid_candidates and uploaded_study_uid not in study_uid_candidates:
        reasons.append(
            "Uploaded DICOM StudyInstanceUID does not match the StudyInstanceUID referenced in prior radiologist notes or order metadata."
        )

    mismatch = bool(reasons)
    return {
        "StudyInstanceUID": uploaded_study_uid,
        "DICOMAccessionNumber": uploaded_accession,
        "dicom_order_mismatch": mismatch,
        "dicom_order_mismatch_warning": _DICOM_ORDER_MISMATCH_WARNING if mismatch else None,
        "dicom_order_mismatch_reasons": reasons or None,
    }

def _as_str_list(items: Any) -> list[str]:
    if not items:
        return []
    if isinstance(items, list):
        out: list[str] = []
        for it in items:
            if isinstance(it, str):
                out.append(it)
            elif isinstance(it, dict):
                out.append(str(it.get("code") or it.get("id") or it.get("term") or json.dumps(it, ensure_ascii=False)))
            else:
                out.append(str(it))
        return out
    if isinstance(items, str):
        return [items]
    return [str(items)]


def _print_block(title: str, payload: Any) -> None:
    print(f"\n===== {title} =====", flush=True)
    try:
        print(json.dumps(payload, indent=2, ensure_ascii=False), flush=True)
    except Exception:  # noqa: BLE001
        print(str(payload), flush=True)


def _job_print(job_id: str, title: str, payload: Any) -> None:
    _print_block(f"JOB {job_id} — {title}", payload)


def _build_clinical_report_text(
    safety_normalized_output: dict[str, Any] | None,
    *,
    doctor_notes: str,
    radiologist_notes: str,
) -> str:
    sn = safety_normalized_output or {}
    structured = sn.get("structured_report")
    if isinstance(structured, dict) and structured:
        indication = str(structured.get("indication") or "").strip()
        technique = str(structured.get("technique") or "").strip()
        impression = str(structured.get("impression") or "").strip()
        findings = structured.get("findings") or []

        findings_lines: list[str] = []
        if isinstance(findings, list):
            for f in findings:
                if isinstance(f, dict):
                    label = str(f.get("label") or "").strip()
                    location = str(f.get("location") or "").strip()
                    status = str(f.get("status") or "").strip()
                    parts = [p for p in [label, location, status] if p]
                    if parts:
                        findings_lines.append("- " + " | ".join(parts))
                elif isinstance(f, str) and f.strip():
                    findings_lines.append("- " + f.strip())

        sections: list[str] = []
        if indication:
            sections.append("INDICATION:\n" + indication)
        if technique:
            sections.append("TECHNIQUE:\n" + technique)
        if findings_lines:
            sections.append("FINDINGS:\n" + "\n".join(findings_lines))
        if impression:
            sections.append("IMPRESSION:\n" + impression)

        text = "\n\n".join(sections).strip()
        if text:
            return text

    corrected_rad = str(sn.get("corrected_radiologist_notes") or "").strip()
    if corrected_rad:
        return corrected_rad
    if radiologist_notes.strip():
        return radiologist_notes.strip()
    if doctor_notes.strip():
        return doctor_notes.strip()
    return "No clinical report text available."


def _build_report_filling_body(
    *,
    patient_id: str,
    patient_name: str,
    order_id: str,
    order_date: str,
    date_of_birth: str,
    national_id: str,
    gender: str,
    accession_number: str,
    modality: str,
    body_part: str,
    study_date: str,
    view_position: str = "",
    patient_age: str = "",
    pixel_spacing: Any = None,
    OutputLanguage: str,
    exam_type: str = "",
    doctor_notes: str = "",
    radiologist_notes: str = "",
    signing_physician: str = "",
    signing_physician_code: str = "",
    ai_interpretation: dict[str, Any] | None = None,
    qc_result: dict[str, Any] | None = None,
    dicom_extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dicom_payload = {
        "PatientID": patient_id,
        "PatientName": patient_name,
        "OrderID": order_id,
        "OrderDate": order_date or None,
        "DateOfBirth": date_of_birth or None,
        "NationalID": national_id,
        "Gender": gender,
        "AccessionNumber": accession_number,
        "Modality": modality,
        "BodyPartExamined": body_part,
        "StudyDate": study_date,
        "ViewPosition": view_position or None,
        "PatientAge": patient_age or None,
        "PixelSpacing": pixel_spacing,
    }
    if isinstance(dicom_extras, dict):
        dicom_payload.update(dicom_extras)

    # Surface the AI (torchxrayvision CNN) interpretation so the report reflects it.
    ai_summary = None
    effective_radiologist_notes = radiologist_notes
    if isinstance(ai_interpretation, dict):
        _findings = ai_interpretation.get("findings") or []
        _codes = [f.get("finding_code") for f in _findings
                  if isinstance(f, dict) and f.get("finding_code")]
        _readable = [str(c).replace("_", " ").title() for c in _codes]
        ai_summary = {
            "summary": ai_interpretation.get("summary") or "",
            "status": ai_interpretation.get("status") or "",
            "findings_count": len(_findings),
            "findings": _readable,
        }
        # No human radiologist in the automated pipeline: let the AI findings drive
        # the report (RadiologistNotes is the report-filler's primary findings source).
        if not (radiologist_notes or "").strip() and _readable:
            effective_radiologist_notes = (
                f"AI-detected findings ({(modality or '').strip()} {(body_part or '').strip()}): "
                + "; ".join(_readable) + "."
            )

    return {
        "PatientID": patient_id,
        "PatientName": patient_name,
        "OrderID": order_id,
        "OrderDate": order_date or None,
        "DateOfBirth": date_of_birth or None,
        "NationalID": national_id,
        "Gender": gender,
        "AccessionNumber": accession_number,
        "OutputLanguage": OutputLanguage,
        "ExamType": exam_type or None,
        "DoctorNotes": doctor_notes or None,
        "RadiologistNotes": effective_radiologist_notes or None,
        "SigningPhysician": signing_physician or None,
        "SigningPhysicianCode": signing_physician_code or None,
        "AIInterpretation": ai_interpretation or None,
        "AIInterpretationSummary": ai_summary,
        "QCResult": qc_result or None,
        "DICOM": dicom_payload,
    }


def _empty_final_report() -> dict[str, Any]:
    return {
        "ID": 0,
        "TEMPLATE_NAME": "",
        "TEMPLATE_TEXT": "",
        "STATUS_ID": None,
        "CREATED_BY": None,
        "CREATION_DATETIME": None,
        "DELETED_BY": None,
        "DELETE_DATETIME": None,
        "UPDATED_BY": None,
        "UPDATE_DATETIME": None,
        "Physician": None,
    }


def _build_delivery_preview(
    summary: dict[str, Any] | None,
    *,
    exam_type: str,
    accession_number: str,
    patient_id: str,
    qc_status: str | None,
    dicom_order_mismatch_warning: str | None = None,
) -> dict[str, str]:
    report = summary if isinstance(summary, dict) else {}
    template_text = str(report.get("TEMPLATE_TEXT") or "").strip()
    template_name = str(report.get("TEMPLATE_NAME") or "").strip()
    subject_prefix = _DICOM_ORDER_MISMATCH_SUBJECT_PREFIX if dicom_order_mismatch_warning else ""
    subject = f"{subject_prefix}[AI DRAFT READY] {exam_type} - Accession {accession_number} - Patient {patient_id}"
    body = (
        "=== REPORT DRAFT (Radiologist review required before finalising) ===\n\n"
        f"{template_text or '(no report text returned)'}\n\n"
        "=== QA SUMMARY ===\n"
        f"QC Status: {qc_status or 'UNKNOWN'}\n"
        f"Template Used: {template_name or 'N/A'}\n\n"
        "DISCLAIMER: This is an AI-assisted draft. Board-certified radiologist review is required before any clinical use.\n"
    )
    return {"subject": subject, "body": body}


async def _api_run_pipeline_v2(
    *,
    dicom_file: UploadFile,
    doctor_notes: str,
    radiologist_notes: str,
    exam_type: str,
    patient_id: str,
    patient_name: str,
    order_id: str,
    order_date: str,
    date_of_birth: str,
    national_id: str,
    gender: str,
    accession_number: str,
    OutputLanguage: str,
    signing_physician: str,
    signing_physician_code: str,
    modality: str,
    body_part: str,
    study_date: str,
    qa_override: str,
) -> JSONResponse:
    _print_block(
        "PIPELINE INPUT",
        {
            "file_name": dicom_file.filename,
            "file_type": dicom_file.content_type,
            "doctor_notes": doctor_notes,
            "radiologist_notes": radiologist_notes,
            "exam_type": exam_type,
            "patient_id": patient_id,
            "patient_name": patient_name,
            "order_id": order_id,
            "order_date": order_date,
            "date_of_birth": date_of_birth,
            "national_id": national_id,
            "gender": gender,
            "accession_number": accession_number,
            "OutputLanguage": OutputLanguage,
            "signing_physician": signing_physician,
            "signing_physician_code": signing_physician_code,
            "modality": modality,
            "body_part": body_part,
            "study_date": study_date,
            "qa_override": qa_override,
        },
    )

    status = await ensure_services_running(start_missing=False)
    down = [s for s in status["services"] if not s["running"]]
    if down:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "One or more services are down. Start services first.",
                "services": down,
            },
        )

    original_bytes = await dicom_file.read()
    original_name = dicom_file.filename or "dicom.zip"
    if not original_bytes:
        raise HTTPException(status_code=400, detail="Empty upload")

    try:
        upload_name, dicom_bytes = _as_zip_bytes(original_name, original_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    content_type = dicom_file.content_type or (
        "application/zip" if upload_name.lower().endswith(".zip") else "application/dicom"
    )
    if not dicom_bytes:
        raise HTTPException(status_code=400, detail="Empty upload")

    resolved_meta = _merged_upload_metadata(
        upload_name,
        dicom_bytes,
        modality=modality,
        study_date=study_date,
        patient_name=patient_name,
        patient_sex=gender,
    )
    try:
        parsed_dicom = _extract_parse_dicom_payload(upload_name, dicom_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unable to parse uploaded DICOM identity for mismatch check: %s", exc)
        parsed_dicom = {}
    mismatch_context = _build_dicom_order_mismatch_context(
        parsed_dicom,
        order_accession=accession_number,
        radiologist_notes=radiologist_notes,
        order_metadata={"AccessionNumber": accession_number},
    )
    resolved_modality = str(resolved_meta.get("modality") or modality)
    resolved_study_date = str(resolved_meta.get("study_date") or study_date)
    resolved_view_position = str(resolved_meta.get("view_position") or "")
    resolved_patient_name = str(resolved_meta.get("patient_name") or patient_name)
    resolved_patient_sex = str(resolved_meta.get("patient_sex") or gender)
    resolved_patient_age = str(resolved_meta.get("patient_age") or "")
    resolved_pixel_spacing = resolved_meta.get("pixel_spacing")

    results: dict[str, Any] = {
        "input": {
            "patient_id": patient_id,
            "modality": resolved_modality,
            "OutputLanguage": OutputLanguage,
            "study_date": resolved_study_date,
            "view_position": resolved_view_position or None,
            "patient_name": resolved_patient_name,
            "patient_sex": resolved_patient_sex,
            "patient_age": resolved_patient_age or None,
            "pixel_spacing": resolved_pixel_spacing,
            "uploaded_dicom_accession_number": mismatch_context.get("DICOMAccessionNumber"),
            "uploaded_dicom_study_instance_uid": mismatch_context.get("StudyInstanceUID"),
            "dicom_order_mismatch": mismatch_context.get("dicom_order_mismatch"),
            "dicom_order_mismatch_warning": mismatch_context.get("dicom_order_mismatch_warning"),
        }
    }
    override_enabled = str(qa_override).strip().lower() in {"1", "true", "yes", "y"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        qc_url = qc_endpoint_for_modality(resolved_modality)
        _print_block(
            "STAGE 1 REQUEST (Image QA)",
            {
                "url": qc_url,
                "file_name": upload_name,
                "file_size_bytes": len(dicom_bytes),
                "resolved_modality": resolved_modality,
                "use_gpt_report": False,
                "OutputLanguage": OutputLanguage,
                "qa_override": override_enabled,
            },
        )
        qc_resp = await client.post(
            qc_url,
            files={"file": (upload_name, dicom_bytes, content_type)},
            data={"use_gpt_report": "false", "OutputLanguage": OutputLanguage},
        )
        try:
            qc_json = qc_resp.json()
        except Exception:  # noqa: BLE001
            qc_json = {"raw": qc_resp.text}
        results["stage_1_image_qa"] = {"status_code": qc_resp.status_code, "response": qc_json}
        _print_block("STAGE 1 RESPONSE (Image QA)", results["stage_1_image_qa"])

        qc_status = (qc_json or {}).get("qc_status")
        qa_pass = qc_status in {"PASS", "WARNING"}
        results["stage_1_image_qa"]["qa_pass"] = qa_pass
        results["stage_1_image_qa"]["qa_override_used"] = override_enabled

        if not qa_pass:
            results["workflow"] = {
                "continued_after_stage_1": True,
                "reason": "QA not PASS/WARNING",
                "qc_status": qc_status,
            }
            _print_block("WORKFLOW CONTINUED AFTER QA", results["workflow"])

        interp_url = interpretation_endpoint_for_modality(resolved_modality)
        _print_block(
            "STAGE 2 REQUEST (AI Interpretation)",
            {
                "url": interp_url,
                "file_name": upload_name,
                "file_size_bytes": len(dicom_bytes),
                "resolved_modality": resolved_modality,
                "OutputLanguage": OutputLanguage,
            },
        )
        interp_resp = await client.post(
            interp_url,
            files={"file": (upload_name, dicom_bytes, content_type)},
            data={"OutputLanguage": OutputLanguage},
        )
        try:
            interp_json = interp_resp.json()
        except Exception:  # noqa: BLE001
            interp_json = {"raw": interp_resp.text}
        results["stage_2_ai_interpretation"] = {"status_code": interp_resp.status_code, "response": interp_json}
        _print_block("STAGE 2 RESPONSE (AI Interpretation)", results["stage_2_ai_interpretation"])

        stage3_body = _build_report_filling_body(
            patient_id=patient_id,
            patient_name=resolved_patient_name,
            order_id=order_id,
            order_date=order_date,
            date_of_birth=date_of_birth,
            national_id=national_id,
            gender=resolved_patient_sex,
            accession_number=accession_number,
            modality=resolved_modality,
            body_part=body_part,
            study_date=resolved_study_date,
            view_position=resolved_view_position,
            patient_age=resolved_patient_age,
            pixel_spacing=resolved_pixel_spacing,
            OutputLanguage=OutputLanguage,
            exam_type=exam_type,
            doctor_notes=doctor_notes,
            radiologist_notes=radiologist_notes,
            signing_physician=signing_physician,
            signing_physician_code=signing_physician_code,
            ai_interpretation=interp_json if isinstance(interp_json, dict) else None,
            qc_result=qc_json if isinstance(qc_json, dict) else None,
            dicom_extras=mismatch_context,
        )
        stage3_url = f"{_REPORT}/api/v1/report-filling"
        _print_block("STAGE 3 REQUEST (Final Report Filling)", {"url": stage3_url, "json": stage3_body})
        report_resp = await client.post(stage3_url, json=stage3_body)
        try:
            report_json = report_resp.json()
        except Exception:  # noqa: BLE001
            report_json = {"raw": report_resp.text}
        results["stage_3_report_filling"] = {"status_code": report_resp.status_code, "response": report_json}
        _print_block("STAGE 3 RESPONSE (Final Report Filling)", results["stage_3_report_filling"])

        skipped_reason = "Unified report-filling contract replaces legacy matching/autofill stages."
        results["stage_4_analysis_matching"] = {"status": "skipped", "reason": skipped_reason}
        results["stage_5_template_autofill"] = {"status": "skipped", "reason": skipped_reason}

        summary = report_json if isinstance(report_json, dict) else _empty_final_report()
        results["summary"] = summary
        results["output_record"] = summary
        results["delivery_preview"] = _build_delivery_preview(
            summary,
            exam_type=exam_type,
            accession_number=accession_number,
            patient_id=patient_id,
            qc_status=qc_status,
            dicom_order_mismatch_warning=mismatch_context.get("dicom_order_mismatch_warning"),
        )
        _print_block(
            "PIPELINE DONE (Summary)",
            {
                "summary": summary,
                "delivery_preview_subject": results["delivery_preview"]["subject"],
            },
        )

        if report_resp.is_success and isinstance(report_json, dict):
            return JSONResponse(report_json, status_code=report_resp.status_code)

        return JSONResponse(results, status_code=report_resp.status_code)


async def _run_pipeline_job_v2(job: "_Job") -> None:
    p = job.payload
    qa_override = bool(p.get("qa_override", False))
    output_language = str(p.get("OutputLanguage") or "el")

    try:
        _job_print(job.job_id, "PIPELINE INPUT", p)
        await job.emit("job_status", {"status": "running", "message": "Starting pipeline"})

        status = await ensure_services_running(start_missing=False)
        down = [s for s in status["services"] if not s["running"]]
        await job.emit("services", status)
        if down:
            job.status = "failed"
            job.message = "One or more services are down"
            _job_print(job.job_id, "SERVICES DOWN", down)
            await job.emit("job_status", {"status": job.status, "message": job.message, "down": down})
            return

        resolved_meta = _merged_upload_metadata(
            job.upload_name,
            job.dicom_bytes,
            modality=str(p.get("modality") or ""),
            study_date=str(p.get("study_date") or ""),
            patient_name=str(p.get("patient_name") or ""),
            patient_sex=str(p.get("gender") or ""),
        )
        try:
            parsed_dicom = _extract_parse_dicom_payload(job.upload_name, job.dicom_bytes)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unable to parse uploaded DICOM identity for mismatch check: %s", exc)
            parsed_dicom = {}
        mismatch_context = _build_dicom_order_mismatch_context(
            parsed_dicom,
            order_accession=str(p.get("accession_number") or ""),
            radiologist_notes=str(p.get("radiologist_notes") or ""),
            order_metadata={"AccessionNumber": str(p.get("accession_number") or "")},
        )
        resolved_modality = str(resolved_meta.get("modality") or p.get("modality") or "")
        resolved_study_date = str(resolved_meta.get("study_date") or p.get("study_date") or "")
        resolved_view_position = str(resolved_meta.get("view_position") or "")
        resolved_patient_name = str(resolved_meta.get("patient_name") or p.get("patient_name") or "")
        resolved_patient_sex = str(resolved_meta.get("patient_sex") or p.get("gender") or "")
        resolved_patient_age = str(resolved_meta.get("patient_age") or "")
        resolved_pixel_spacing = resolved_meta.get("pixel_spacing")

        results: dict[str, Any] = {
            "input": {
                "patient_id": p["patient_id"],
                "modality": resolved_modality,
                "OutputLanguage": output_language,
                "study_date": resolved_study_date,
                "view_position": resolved_view_position or None,
                "patient_name": resolved_patient_name,
                "patient_sex": resolved_patient_sex,
                "patient_age": resolved_patient_age or None,
                "pixel_spacing": resolved_pixel_spacing,
                "uploaded_dicom_accession_number": mismatch_context.get("DICOMAccessionNumber"),
                "uploaded_dicom_study_instance_uid": mismatch_context.get("StudyInstanceUID"),
                "dicom_order_mismatch": mismatch_context.get("dicom_order_mismatch"),
                "dicom_order_mismatch_warning": mismatch_context.get("dicom_order_mismatch_warning"),
            }
        }
        await job.emit("input", p)

        async with httpx.AsyncClient(timeout=120.0) as client:
            qc_url = qc_endpoint_for_modality(resolved_modality)
            _job_print(
                job.job_id,
                "STAGE 1 REQUEST (Image QA)",
                {
                    "url": qc_url,
                    "file_name": job.upload_name,
                    "file_size_bytes": len(job.dicom_bytes),
                    "resolved_modality": resolved_modality,
                    "use_gpt_report": False,
                    "OutputLanguage": output_language,
                    "qa_override": qa_override,
                },
            )
            await job.emit("stage_start", {"stage": 1, "name": "Image QA", "url": qc_url})
            qc_resp = await client.post(
                qc_url,
                files={"file": (job.upload_name, job.dicom_bytes, job.content_type)},
                data={"use_gpt_report": "false", "OutputLanguage": output_language},
            )
            try:
                qc_json = qc_resp.json()
            except Exception:  # noqa: BLE001
                qc_json = {"raw": qc_resp.text}
            results["stage_1_image_qa"] = {"status_code": qc_resp.status_code, "response": qc_json}

            qc_status = (qc_json or {}).get("qc_status")
            qa_pass = qc_status in {"PASS", "WARNING"}
            results["stage_1_image_qa"]["qa_pass"] = qa_pass
            results["stage_1_image_qa"]["qa_override_used"] = qa_override
            _job_print(job.job_id, "STAGE 1 RESPONSE (Image QA)", results["stage_1_image_qa"])
            await job.emit("stage_result", {"stage": 1, "result": results["stage_1_image_qa"]})

            if not qa_pass:
                results["workflow"] = {
                    "continued_after_stage_1": True,
                    "reason": "QA not PASS/WARNING",
                    "qc_status": qc_status,
                }
                _job_print(job.job_id, "WORKFLOW CONTINUED AFTER QA", results["workflow"])

            interp_url = interpretation_endpoint_for_modality(resolved_modality)
            _job_print(
                job.job_id,
                "STAGE 2 REQUEST (AI Interpretation)",
                {
                    "url": interp_url,
                    "file_name": job.upload_name,
                    "file_size_bytes": len(job.dicom_bytes),
                    "resolved_modality": resolved_modality,
                    "OutputLanguage": output_language,
                },
            )
            await job.emit("stage_start", {"stage": 2, "name": "AI Interpretation", "url": interp_url})
            interp_resp = await client.post(
                interp_url,
                files={"file": (job.upload_name, job.dicom_bytes, job.content_type)},
                data={"OutputLanguage": output_language},
            )
            try:
                interp_json = interp_resp.json()
            except Exception:  # noqa: BLE001
                interp_json = {"raw": interp_resp.text}
            results["stage_2_ai_interpretation"] = {"status_code": interp_resp.status_code, "response": interp_json}
            _job_print(job.job_id, "STAGE 2 RESPONSE (AI Interpretation)", results["stage_2_ai_interpretation"])
            await job.emit("stage_result", {"stage": 2, "result": results["stage_2_ai_interpretation"]})

            stage3_body = _build_report_filling_body(
                patient_id=p["patient_id"],
                patient_name=resolved_patient_name,
                order_id=p["order_id"],
                order_date=p["order_date"],
                date_of_birth=p["date_of_birth"],
                national_id=p["national_id"],
                gender=resolved_patient_sex,
                accession_number=p["accession_number"],
                modality=resolved_modality,
                body_part=p["body_part"],
                study_date=resolved_study_date,
                view_position=resolved_view_position,
                patient_age=resolved_patient_age,
                pixel_spacing=resolved_pixel_spacing,
                OutputLanguage=output_language,
                exam_type=str(p.get("exam_type") or ""),
                doctor_notes=str(p.get("doctor_notes") or ""),
                radiologist_notes=str(p.get("radiologist_notes") or ""),
                signing_physician=p.get("signing_physician", ""),
                signing_physician_code=p.get("signing_physician_code", ""),
                ai_interpretation=interp_json if isinstance(interp_json, dict) else None,
                qc_result=qc_json if isinstance(qc_json, dict) else None,
                dicom_extras=mismatch_context,
            )
            stage3_url = f"{_REPORT}/api/v1/report-filling"
            _job_print(
                job.job_id,
                "STAGE 3 REQUEST (Final Report Filling)",
                {"url": stage3_url, "json": stage3_body},
            )
            await job.emit("stage_start", {"stage": 3, "name": "Final Report Filling", "url": stage3_url})
            report_resp = await client.post(stage3_url, json=stage3_body)
            try:
                report_json = report_resp.json()
            except Exception:  # noqa: BLE001
                report_json = {"raw": report_resp.text}
            results["stage_3_report_filling"] = {"status_code": report_resp.status_code, "response": report_json}
            _job_print(job.job_id, "STAGE 3 RESPONSE (Final Report Filling)", results["stage_3_report_filling"])
            await job.emit("stage_result", {"stage": 3, "result": results["stage_3_report_filling"]})

            skipped_reason = "Unified report-filling contract replaces legacy matching/autofill stages."
            results["stage_4_analysis_matching"] = {"status": "skipped", "reason": skipped_reason}
            results["stage_5_template_autofill"] = {"status": "skipped", "reason": skipped_reason}
            await job.emit("stage_result", {"stage": 4, "result": results["stage_4_analysis_matching"]})
            await job.emit("stage_result", {"stage": 5, "result": results["stage_5_template_autofill"]})

            summary = report_json if isinstance(report_json, dict) else _empty_final_report()
            results["output_record"] = summary
            results["summary"] = summary
            results["delivery_preview"] = _build_delivery_preview(
                summary,
                exam_type=p["exam_type"],
                accession_number=p["accession_number"],
                patient_id=p["patient_id"],
                qc_status=qc_status,
                dicom_order_mismatch_warning=mismatch_context.get("dicom_order_mismatch_warning"),
            )

        job.status = "done"
        job.message = "Done"
        job.result = results
        await job.emit("result", results)
        await job.emit("job_status", {"status": job.status, "message": job.message})
        _job_print(
            job.job_id,
            "PIPELINE DONE (Summary)",
            {
                "summary": results.get("summary"),
                "delivery_preview_subject": results["delivery_preview"]["subject"],
            },
        )
    except Exception as e:  # noqa: BLE001
        job.status = "failed"
        job.message = str(e)
        _job_print(job.job_id, "PIPELINE FAILED", {"error": str(e)})
        await job.emit("job_status", {"status": job.status, "message": job.message})
        await job.emit("error", {"message": str(e)})
        return


app = FastAPI(title="Radiology Workflow Launcher", version="0.1.0")


@app.on_event("startup")
async def _startup() -> None:
    print_service_port_map()
    # Always attempt to start any missing local services when this UI launches.
    await ensure_services_running(start_missing=True)


@app.on_event("shutdown")
def _shutdown() -> None:
    for name in list(SERVICE_PROCS.keys()):
        stop_service(name)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    index_path = ROOT / "index.html"
    if not index_path.exists():
        return "<h1>Missing index.html</h1>"
    return index_path.read_text(encoding="utf-8")


@app.get("/api/status")
async def api_status() -> JSONResponse:
    status = await ensure_services_running(start_missing=False)
    status["pacs"] = get_pacs_config_status()
    return JSONResponse(status)


@app.post("/api/start-missing")
async def api_start_missing() -> JSONResponse:
    return JSONResponse(await ensure_services_running(start_missing=True))


@app.post("/api/stop-all")
async def api_stop_all() -> JSONResponse:
    return JSONResponse(stop_all_services())


@app.post("/api/parse-dicom")
async def api_parse_dicom(dicom_file: UploadFile = File(...)) -> JSONResponse:
    original_bytes = await dicom_file.read()
    original_name = dicom_file.filename or "upload.dcm"
    if not original_bytes:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")

    try:
        payload = _extract_parse_dicom_payload(original_name, original_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Failed to parse DICOM metadata: {exc}") from exc

    return JSONResponse(payload)


# ---------------------------------------------------------------------------
# Lean draft-report path (demo): DICOM -> rendered image -> gpt-4o vision -> report.
# Bypasses the multi-service pipeline for a fast, robust single-call assessment.
# ---------------------------------------------------------------------------
import base64 as _base64

_RADIOLOGY_MODEL = os.getenv("RADIOLOGY_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o")
_OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


def _dicom_to_png_b64(dicom_bytes: bytes) -> str:
    """Render the first DICOM frame to a base64 PNG for the vision model."""
    import numpy as np
    from PIL import Image

    ds = pydicom.dcmread(BytesIO(dicom_bytes), force=True)
    arr = ds.pixel_array.astype("float32")
    slope = float(getattr(ds, "RescaleSlope", 1) or 1)
    intercept = float(getattr(ds, "RescaleIntercept", 0) or 0)
    arr = arr * slope + intercept
    lo, hi = np.percentile(arr, [1, 99])
    if hi <= lo:
        lo, hi = float(arr.min()), float(arr.max())
    arr = np.clip((arr - lo) / (hi - lo + 1e-6), 0, 1)
    if str(getattr(ds, "PhotometricInterpretation", "")).upper() == "MONOCHROME1":
        arr = 1.0 - arr
    img = Image.fromarray((arr * 255).astype("uint8"))
    if img.mode != "L":
        img = img.convert("L")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return _base64.b64encode(buf.getvalue()).decode("ascii")


def _gpt4o_radiology_report(png_b64: str, ctx: dict) -> dict:
    """Ask the vision model for a STRUCTURED draft report (JSON)."""
    from openai import OpenAI

    client = OpenAI(base_url=_OPENAI_BASE_URL, api_key=_OPENAI_API_KEY)
    lang = "Arabic" if str(ctx.get("output_language", "")).lower().startswith("ar") else "English"
    system = (
        "You are a board-certified radiologist assistant producing a STRUCTURED DRAFT report "
        "from a single medical image. Return STRICT JSON with keys: technique (string), "
        "findings (string), impression (string), recommendations (array of strings). "
        "ALWAYS populate every key — describe what is actually visible in the image. If the image "
        "quality is limited or it is not a standard diagnostic radiograph, state that explicitly in "
        "'findings' and set 'impression' to 'Non-diagnostic image — clinical correlation and repeat "
        "imaging advised.' Never return an empty object. This is an AI-assisted draft requiring "
        f"radiologist review. Write all text in {lang}."
    )
    user_text = (
        f"Modality: {ctx.get('modality') or 'unknown'}. "
        f"Body part: {ctx.get('body_part') or 'unknown'}. "
        f"Clinical indication: {ctx.get('clinical_indication') or 'not provided'}. "
        f"Patient: {ctx.get('patient_name') or 'unknown'}. Produce the draft report as JSON."
    )
    resp = client.chat.completions.create(
        model=_RADIOLOGY_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png_b64}"}},
            ]},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=900,
    )
    content = resp.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except Exception:
        return {"technique": "", "findings": content, "impression": "", "recommendations": []}


@app.post("/api/draft-report")
async def api_draft_report(request: Request) -> JSONResponse:
    """Demo radiology flow: DICOM upload -> render -> gpt-4o vision -> draft report.

    The form is parsed manually and the upload is accepted under ANY field name
    (dicom_file, file, upload, ...). Declaring a single required field made this
    endpoint brittle: any client/field-name mismatch produced an opaque 422 before
    the handler ever ran.
    """
    _log = logging.getLogger(__name__)
    try:
        form = await request.form()
    except Exception as exc:  # noqa: BLE001
        _log.exception("draft-report: could not parse multipart form")
        raise HTTPException(status_code=422, detail=f"Could not parse upload form: {exc}") from exc

    # First value that looks like an uploaded file, whatever it was named.
    upload = None
    for _key, val in form.multi_items():
        if hasattr(val, "filename") and hasattr(val, "read"):
            upload = val
            break

    def _f(key: str, default: str = "") -> str:
        val = form.get(key)
        return val if isinstance(val, str) else default

    patient_name = _f("patient_name")
    patient_id = _f("patient_id")
    modality = _f("modality")
    body_part = _f("body_part")
    clinical_indication = _f("clinical_indication")
    output_language = _f("output_language", "en") or "en"

    _log.info("draft-report: fields=%s file=%s", list(form.keys()),
              getattr(upload, "filename", None))

    if upload is None:
        raise HTTPException(
            status_code=422,
            detail=("No file was received. Attach the DICOM as a multipart file field "
                    f"(e.g. 'dicom_file'). Fields received: {list(form.keys())}"),
        )
    blob = await upload.read()
    if not blob:
        raise HTTPException(status_code=422, detail="Uploaded file is empty (0 bytes).")
    name = getattr(upload, "filename", None) or "upload.dcm"
    try:
        meta = _extract_parse_dicom_payload(name, blob)  # DICOM-only: raises on non-DICOM
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Not a valid DICOM file: {exc}") from exc
    try:
        png_b64 = _dicom_to_png_b64(blob)
    except Exception as exc:  # noqa: BLE001
        ts = "unknown"
        try:
            _ds = pydicom.dcmread(BytesIO(blob), stop_before_pixels=True, force=True)
            ts = str(getattr(_ds.file_meta, "TransferSyntaxUID", "")) or "unknown"
        except Exception:  # noqa: BLE001
            pass
        logging.getLogger(__name__).exception(
            "DICOM pixel render failed (transfer_syntax=%s, file=%s)", ts, name)
        raise HTTPException(
            status_code=422,
            detail=(f"Could not render DICOM pixels (transfer syntax {ts}): {exc}. "
                    "Compressed DICOMs need a decoder (pylibjpeg/gdcm)."),
        ) from exc
    ctx = {
        "patient_name": patient_name, "patient_id": patient_id, "modality": modality,
        "body_part": body_part, "clinical_indication": clinical_indication,
        "output_language": output_language,
    }
    try:
        report = _gpt4o_radiology_report(png_b64, ctx) or {}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Vision model failed: {exc}") from exc
    # Normalise so the UI always has the four fields.
    recs = report.get("recommendations") or []
    if isinstance(recs, str):
        recs = [recs]
    report = {
        "technique": report.get("technique") or "",
        "findings": report.get("findings") or "No structured findings were generated for this image.",
        "impression": report.get("impression") or "",
        "recommendations": recs,
    }
    return JSONResponse({
        "patient_name": patient_name, "patient_id": patient_id,
        "dicom_metadata": meta, "image_base64": png_b64, "report": report,
        "model": _RADIOLOGY_MODEL,
        "disclaimer": "AI-assisted draft. Board-certified radiologist review required before clinical use.",
    })


@app.post("/api/run-pipeline")
async def api_run_pipeline(
    dicom_file: UploadFile = File(...),
    doctor_notes: str = Form(""),
    radiologist_notes: str = Form(""),
    exam_type: str = Form(""),
    patient_id: str = Form(""),
    patient_name: str = Form(""),
    order_id: str = Form(""),
    order_date: str = Form(""),
    date_of_birth: str = Form(""),
    national_id: str = Form(""),
    gender: str = Form(""),
    accession_number: str = Form(...),
    OutputLanguage: str = Form("el"),
    signing_physician: str = Form(""),
    signing_physician_code: str = Form(""),
    modality: str = Form("CR"),
    body_part: str = Form(""),
    study_date: str = Form(""),
    qa_override: str = Form("false"),
) -> JSONResponse:
    return await _api_run_pipeline_v2(
        dicom_file=dicom_file,
        doctor_notes=doctor_notes,
        radiologist_notes=radiologist_notes,
        exam_type=exam_type,
        patient_id=patient_id,
        patient_name=patient_name,
        order_id=order_id,
        order_date=order_date,
        date_of_birth=date_of_birth,
        national_id=national_id,
        gender=gender,
        accession_number=accession_number,
        OutputLanguage=OutputLanguage,
        signing_physician=signing_physician,
        signing_physician_code=signing_physician_code,
        modality=modality,
        body_part=body_part,
        study_date=study_date,
        qa_override=qa_override,
    )

    _print_block(
        "PIPELINE INPUT",
        {
            "file_name": dicom_file.filename,
            "file_type": dicom_file.content_type,
            "doctor_notes": doctor_notes,
            "radiologist_notes": radiologist_notes,
            "exam_type": exam_type,
            "patient_id": patient_id,
            "patient_name": patient_name,
            "order_id": order_id,
            "order_date": order_date,
            "date_of_birth": date_of_birth,
            "national_id": national_id,
            "gender": gender,
            "accession_number": accession_number,
            "OutputLanguage": OutputLanguage,
            "modality": modality,
            "body_part": body_part,
            "study_date": study_date,
            "qa_override": qa_override,
        },
    )

    # Ensure services are up before running.
    status = await ensure_services_running(start_missing=False)
    down = [s for s in status["services"] if not s["running"]]
    if down:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "One or more services are down. Start services first.",
                "services": down,
            },
        )

    original_bytes = await dicom_file.read()
    original_name = dicom_file.filename or "dicom.zip"
    if not original_bytes:
        raise HTTPException(status_code=400, detail="Empty upload")

    try:
        upload_name, dicom_bytes = _as_zip_bytes(original_name, original_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    content_type = dicom_file.content_type or (
        "application/zip" if upload_name.lower().endswith(".zip") else "application/dicom"
    )
    if not dicom_bytes:
        raise HTTPException(status_code=400, detail="Empty upload")

    results: dict[str, Any] = {"input": {"patient_id": patient_id, "modality": modality}}
    override_enabled = str(qa_override).strip().lower() in {"1", "true", "yes", "y"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        # Stage 1 — QC
        qc_url = qc_endpoint_for_modality(modality)
        _print_block(
            "STAGE 1 REQUEST (Image QA)",
            {
                "url": qc_url,
                "file_name": upload_name,
                "file_size_bytes": len(dicom_bytes),
                "use_gpt_report": False,
                "OutputLanguage": OutputLanguage,
                "qa_override": override_enabled,
            },
        )
        qc_resp = await client.post(
            qc_url,
            files={"file": (upload_name, dicom_bytes, content_type)},
            data={"use_gpt_report": "false", "OutputLanguage": OutputLanguage},
        )
        results["stage_1_image_qa"] = {"status_code": qc_resp.status_code}
        qc_json: dict[str, Any] | None = None
        try:
            qc_json = qc_resp.json()
        except Exception:  # noqa: BLE001
            qc_json = {"raw": qc_resp.text}
        results["stage_1_image_qa"]["response"] = qc_json
        _print_block("STAGE 1 RESPONSE (Image QA)", results["stage_1_image_qa"])

        qc_status = (qc_json or {}).get("qc_status")
        qa_pass = qc_status in {"PASS", "WARNING"}
        results["stage_1_image_qa"]["qa_pass"] = qa_pass
        results["stage_1_image_qa"]["qa_override_used"] = override_enabled

        if not qa_pass:
            results["workflow"] = {
                "continued_after_stage_1": True,
                "reason": "QA not PASS/WARNING",
                "qc_status": qc_status,
            }
            _print_block("WORKFLOW CONTINUED AFTER QA", results["workflow"])

        # Stage 2 — Interpretation
        interp_url = interpretation_endpoint_for_modality(modality)
        _print_block(
            "STAGE 2 REQUEST (AI Interpretation)",
            {
                "url": interp_url,
                "file_name": upload_name,
                "file_size_bytes": len(dicom_bytes),
                "OutputLanguage": OutputLanguage,
            },
        )
        interp_resp = await client.post(
            interp_url,
            files={"file": (upload_name, dicom_bytes, content_type)},
            data={"OutputLanguage": OutputLanguage},
        )
        results["stage_2_ai_interpretation"] = {"status_code": interp_resp.status_code}
        try:
            interp_json = interp_resp.json()
        except Exception:  # noqa: BLE001
            interp_json = {"raw": interp_resp.text}
        results["stage_2_ai_interpretation"]["response"] = interp_json
        _print_block("STAGE 2 RESPONSE (AI Interpretation)", results["stage_2_ai_interpretation"])

        # Stage 3 — Report correction
        stage3_body = {
            "doctor_notes": doctor_notes,
            "radiologist_notes": radiologist_notes,
            "exam_type": exam_type,
            "extracted_dicom_metadata": {
                "PatientID": patient_id,
                "PatientName": patient_name,
                "OrderID": order_id,
                "OrderDate": order_date,
                "DateOfBirth": date_of_birth,
                "NationalID": national_id,
                "Gender": gender,
                "AccessionNumber": accession_number,
                "Modality": modality,
                "BodyPartExamined": body_part,
                "ViewPosition": "PA",
                "StudyDate": study_date,
            },
        }
        _print_block("STAGE 3 REQUEST (Report Correction)", {"url": f"{_REPORT}/api/v1/report-correction", "json": stage3_body})
        rc_resp = await client.post(
            f"{_REPORT}/api/v1/report-correction",
            json=stage3_body,
        )
        results["stage_3_report_correction"] = {"status_code": rc_resp.status_code}
        try:
            rc_json = rc_resp.json()
        except Exception:  # noqa: BLE001
            rc_json = {"raw": rc_resp.text}
        results["stage_3_report_correction"]["response"] = rc_json
        _print_block("STAGE 3 RESPONSE (Report Correction)", results["stage_3_report_correction"])

        rc_sn = rc_json.get("safety_normalized_output") if isinstance(rc_json, dict) else {}
        clinical_report_text = _build_clinical_report_text(
            rc_sn if isinstance(rc_sn, dict) else {},
            doctor_notes=doctor_notes,
            radiologist_notes=radiologist_notes,
        )
        results["stage_3_report_correction"]["clinical_report_text"] = clinical_report_text
        _print_block("STAGE 3 DERIVED clinical_report_text", clinical_report_text)

        # Stage 4 — Analysis matching
        stage4_body = {
            "clinical_report": clinical_report_text or "",
            "ai_image_analysis": {"findings": (interp_json or {}).get("findings", [])},
            "extracted_dicom_metadata": {
                "Modality": modality,
                "ViewPosition": "PA",
                "StudyDescription": exam_type,
            },
        }
        _print_block("STAGE 4 REQUEST (Analysis Matching)", {"url": f"{_REPORT}/api/v1/analysis-matching", "json": stage4_body})
        am_resp = await client.post(
            f"{_REPORT}/api/v1/analysis-matching",
            json=stage4_body,
        )
        results["stage_4_analysis_matching"] = {"status_code": am_resp.status_code}
        try:
            am_json = am_resp.json()
        except Exception:  # noqa: BLE001
            am_json = {"raw": am_resp.text}
        results["stage_4_analysis_matching"]["response"] = am_json
        _print_block("STAGE 4 RESPONSE (Analysis Matching)", results["stage_4_analysis_matching"])

        # Stage 5 — Template autofill
        sn = am_json.get("safety_normalized_output") if isinstance(am_json, dict) else {}
        reconciled_findings = (sn or {}).get("reconciled_findings", [])

        icd10_codes_raw = (((rc_sn or {}).get("rag_grounding") or {}).get("icd10_codes")) or []
        icd10_codes_str = _as_str_list(icd10_codes_raw)

        input_data = (
            f"Exam: {exam_type}. Patient ID: {patient_id}. "
            f"Clinical report: {clinical_report_text}. "
            f"Reconciled findings: {json.dumps(reconciled_findings)}. "
            f"ICD-10 codes: {', '.join(icd10_codes_str)}."
        )

        stage5_body = {
            "input_data": input_data,
            "patient_context": {
                "PatientID": patient_id,
                "PatientName": patient_name,
                "OrderID": order_id,
                "AccessionNumber": accession_number,
                "Gender": gender,
                "DateOfBirth": date_of_birth,
                "Modality": modality,
                "StudyDate": study_date,
            },
            "top_k": 3,
        }
        _print_block("STAGE 5 REQUEST (Template Autofill)", {"url": f"{_AUTOFILL}/select-and-fill", "json": stage5_body})
        ta_resp = await client.post(
            f"{_AUTOFILL}/select-and-fill",
            json=stage5_body,
        )
        results["stage_5_template_autofill"] = {"status_code": ta_resp.status_code}
        try:
            ta_json = ta_resp.json()
        except Exception:  # noqa: BLE001
            ta_json = {"raw": ta_resp.text}
        results["stage_5_template_autofill"]["response"] = ta_json
        _print_block("STAGE 5 RESPONSE (Template Autofill)", results["stage_5_template_autofill"])

        missing_fields = (
            ((ta_json.get("autofill") or {}).get("missing_required_fields")) if isinstance(ta_json, dict) else None
        ) or []
        missing_fields_str = _as_str_list(missing_fields)

        critical_alert = bool((interp_json or {}).get("critical_alert", False))
        rendered_report = (ta_json.get("autofill") or {}).get("rendered_report") if isinstance(ta_json, dict) else ""
        template_name = (
            (ta_json.get("selection") or {}).get("selected_template_name") if isinstance(ta_json, dict) else ""
        )
        template_id = (
            (ta_json.get("selection") or {}).get("selected_template_id") if isinstance(ta_json, dict) else ""
        )
        autofill_conf = (
            ((ta_json.get("autofill") or {}).get("confidence_score")) if isinstance(ta_json, dict) else ""
        )
        icd10_str = json.dumps(icd10_codes_raw, ensure_ascii=False)
        rc_warnings = ((rc_json.get("safety_normalized_output") or {}).get("warnings")) if isinstance(rc_json, dict) else []
        warnings_str = json.dumps(rc_warnings, ensure_ascii=False)
        missing_str = ", ".join(missing_fields_str) if missing_fields_str else "None"

        template_text = (
            f"{rendered_report or ''}\n\n"
            f"=== QA SUMMARY ===\n"
            f"QC Status: {qc_status}\n"
            f"Autofill Confidence: {autofill_conf}\n"
            f"Critical AI Alert: {critical_alert}\n\n"
            f"=== ICD-10 CODES ===\n{icd10_str}\n\n"
            f"=== WARNINGS ===\n{warnings_str}\n\n"
            f"=== MISSING FIELDS ===\n{missing_str}\n\n"
            f"DISCLAIMER: AI-assisted draft. Radiologist review required."
        )

        output_record = {
            "ID": template_id,
            "TEMPLATE_NAME": template_name,
            "TEMPLATE_TEXT": template_text,
            "STATUS_ID": None,
            "CREATED_BY": patient_id or "",
            "CREATION_DATETIME": None,
            "DELETED_BY": None,
            "DELETE_DATETIME": None,
            "UPDATED_BY": None,
            "UPDATE_DATETIME": None,
            "Physician": doctor_notes[:120],
            "PatientID": patient_id or "",
            "PatientName": patient_name or "",
            "OrderID": order_id or "",
            "OrderDate": order_date or None,
            "DateOfBirth": date_of_birth or None,
            "NationalID": national_id or "",
            "Gender": gender or "",
            "AccessionNumber": accession_number or "",
            "qc_status": qc_status,
            "critical_alert": critical_alert,
            "missing_required_fields": missing_fields_str,
        }

        results["output_record"] = output_record
        results["summary"] = output_record

        subject_prefix = "🚨 CRITICAL ALERT — Immediate radiologist review required — " if critical_alert else ""
        subject = f"{subject_prefix}[AI DRAFT READY] {exam_type} — Accession {accession_number} — Patient {patient_id}"

        missing_line = f"⚠️ Missing fields: {', '.join(missing_fields_str)}\n\n" if missing_fields_str else ""
        body = (
            "=== REPORT DRAFT (Radiologist review required before finalising) ===\n\n"
            f"{rendered_report}\n\n"
            "=== QA SUMMARY ===\n"
            f"QC Status: {qc_status}\n"
            f"Template Used: {template_used}\n"
            f"Autofill Confidence: {autofill_conf}\n"
            f"Critical AI Alert: {critical_alert}\n\n"
            "=== WARNINGS ===\n"
            f"{json.dumps(rc_warnings, ensure_ascii=False)}\n\n"
            "=== ICD-10 CODES ===\n"
            f"{json.dumps(icd10_codes_raw, ensure_ascii=False)}\n\n"
            f"{missing_line}"
            "DISCLAIMER: This is an AI-assisted draft. Board-certified radiologist review is required before any clinical use.\n"
        )

        results["delivery_preview"] = {"subject": subject, "body": body}
        _print_block("PIPELINE DONE (Summary)", {"summary": results["summary"], "delivery_preview_subject": subject})

    return JSONResponse(results)


class JobStatus(BaseModel):
    job_id: str
    status: Literal["running", "paused", "failed", "done"]
    message: str | None = None


class PacsOrderInput(BaseModel):
    PatientID: str = ""
    PatientName: str = ""
    OrderID: str = ""
    OrderDate: datetime | None = None
    DateOfBirth: datetime | None = None
    NationalID: str = ""
    Gender: str = ""
    AccessionNumber: str
    OutputLanguage: str = "el"
    signing_physician: str = ""
    signing_physician_code: str = ""
    doctor_notes: str = ""
    radiologist_notes: str = ""
    exam_type: str = ""
    qa_override: bool = False


class _Job:
    def __init__(self, job_id: str, payload: dict[str, Any], dicom_bytes: bytes, upload_name: str, content_type: str):
        self.job_id = job_id
        self.payload = payload
        self.dicom_bytes = dicom_bytes
        self.upload_name = upload_name
        self.content_type = content_type
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.status: Literal["running", "paused", "failed", "done"] = "running"
        self.message: str | None = None
        self.result: dict[str, Any] | None = None
        self.task: asyncio.Task[None] | None = None

    async def emit(self, event: str, data: Any) -> None:
        await self.queue.put({"event": event, "data": data})


JOBS: dict[str, _Job] = {}


def _bool_from_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _format_optional_datetime(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _build_job_payload(order_fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "doctor_notes": str(order_fields.get("doctor_notes") or ""),
        "radiologist_notes": str(order_fields.get("radiologist_notes") or ""),
        "exam_type": str(order_fields.get("exam_type") or ""),
        "patient_id": str(order_fields.get("patient_id") or ""),
        "patient_name": str(order_fields.get("patient_name") or ""),
        "order_id": str(order_fields.get("order_id") or ""),
        "order_date": str(order_fields.get("order_date") or ""),
        "date_of_birth": str(order_fields.get("date_of_birth") or ""),
        "national_id": str(order_fields.get("national_id") or ""),
        "gender": str(order_fields.get("gender") or ""),
        "accession_number": str(order_fields.get("accession_number") or ""),
        "OutputLanguage": str(order_fields.get("OutputLanguage") or "el"),
        "signing_physician": str(order_fields.get("signing_physician") or ""),
        "signing_physician_code": str(order_fields.get("signing_physician_code") or ""),
        "modality": str(order_fields.get("modality", "CR") or ""),
        "body_part": str(order_fields.get("body_part") or ""),
        "study_date": str(order_fields.get("study_date") or ""),
        "qa_override": _bool_from_flag(order_fields.get("qa_override", False)),
    }


def _build_order_fields_from_pacs_input(order: PacsOrderInput) -> dict[str, Any]:
    return {
        "doctor_notes": order.doctor_notes,
        "radiologist_notes": order.radiologist_notes,
        "exam_type": order.exam_type,
        "patient_id": order.PatientID,
        "patient_name": order.PatientName,
        "order_id": order.OrderID,
        "order_date": _format_optional_datetime(order.OrderDate),
        "date_of_birth": _format_optional_datetime(order.DateOfBirth),
        "national_id": order.NationalID,
        "gender": order.Gender,
        "accession_number": order.AccessionNumber,
        "OutputLanguage": order.OutputLanguage,
        "signing_physician": order.signing_physician,
        "signing_physician_code": order.signing_physician_code,
        # These are still resolved from the DICOM payload by the existing metadata helpers.
        "modality": "",
        "body_part": "",
        "study_date": "",
        "qa_override": order.qa_override,
    }


def _required_pacs_settings() -> list[tuple[str, Any]]:
    protocol = str(PACS_PROTOCOL or "dicomweb").strip().lower()
    if protocol == "dimse":
        return [
            ("PACS_HOST", PACS_HOST),
            ("PACS_MOVE_DESTINATION_AE", PACS_MOVE_DESTINATION_AE),
        ]
    return [("PACS_BASE_URL", PACS_BASE_URL)]


def get_pacs_config_status() -> dict[str, Any]:
    """Return a non-secret summary of PACS configuration readiness."""
    protocol = str(PACS_PROTOCOL or "dicomweb").strip().lower()
    required_settings = _required_pacs_settings()
    missing_settings = [name for name, value in required_settings if value in (None, "")]
    return {
        "pacs_enabled": PACS_ENABLED,
        "pacs_protocol": protocol,
        "pacs_configured": not missing_settings,
        "missing_settings": missing_settings,
    }


def _get_pacs_connection_settings() -> dict[str, str | int | float | bool | None]:
    return {
        "protocol": PACS_PROTOCOL,
        "enabled": PACS_ENABLED,
        "base_url": PACS_BASE_URL,
        "auth_token_configured": bool(PACS_AUTH_TOKEN),
        "username": PACS_USERNAME,
        "host": PACS_HOST,
        "port": PACS_PORT,
        "ae_title": PACS_AE_TITLE,
        "remote_ae_title": PACS_REMOTE_AE_TITLE,
        "move_destination_ae": PACS_MOVE_DESTINATION_AE,
        "timeout_seconds": PACS_TIMEOUT_SECONDS,
    }


def fetch_dicom_from_pacs(accession_number: str) -> bytes:
    settings = _get_pacs_connection_settings()
    config_status = get_pacs_config_status()
    logger.info("PACS retrieval requested for accession %s", accession_number)
    logger.debug("Current PACS settings keys: %s", sorted(settings))
    if not PACS_ENABLED:
        raise RuntimeError(
            "PACS retrieval is disabled. Set PACS_ENABLED=true and configure PACS_* environment variables to enable it."
        )
    if not config_status["pacs_configured"]:
        missing_settings = ", ".join(config_status["missing_settings"])
        raise RuntimeError(f"PACS is enabled but misconfigured. Missing settings: {missing_settings}")
    # TODO: Use PACS_BASE_URL/PACS credentials for a DICOMweb QIDO-RS lookup by accession number.
    # TODO: Retrieve study bytes with WADO-RS or a pynetdicom C-MOVE/C-GET client once PACS is configured.
    protocol = str(PACS_PROTOCOL or "dicomweb").strip().lower()
    if protocol == "dimse":
        raise NotImplementedError(
            "DIMSE C-FIND/C-MOVE retrieval not yet implemented. "
            f"Implement C-FIND by AccessionNumber against {PACS_HOST}:{PACS_PORT} "
            f"(AE: {PACS_REMOTE_AE_TITLE}) using pynetdicom, then C-MOVE/C-GET to retrieve the study."
        )
    raise NotImplementedError(
        "DICOMweb WADO-RS retrieval not yet implemented. "
        f"Implement QIDO-RS query by AccessionNumber against {PACS_BASE_URL}, "
        "then WADO-RS retrieve for the matched StudyInstanceUID."
    )


async def _create_job_from_dicom_bytes(
    dicom_bytes: bytes,
    upload_name: str,
    order_fields: dict[str, Any],
    *,
    content_type: str | None = None,
) -> JSONResponse:
    if not dicom_bytes:
        raise HTTPException(status_code=400, detail="Empty upload")

    try:
        normalized_upload_name, normalized_dicom_bytes = _as_zip_bytes(upload_name, dicom_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resolved_content_type = content_type or (
        "application/zip" if normalized_upload_name.lower().endswith(".zip") else "application/dicom"
    )

    job_id = uuid.uuid4().hex
    payload = _build_job_payload(order_fields)
    job = _Job(
        job_id,
        payload=payload,
        dicom_bytes=normalized_dicom_bytes,
        upload_name=normalized_upload_name,
        content_type=resolved_content_type,
    )
    JOBS[job_id] = job
    job.task = asyncio.create_task(_run_pipeline_job(job))
    return JSONResponse({"job_id": job_id})


async def _run_pipeline_job(job: _Job) -> None:
    return await _run_pipeline_job_v2(job)

    p = job.payload
    qa_override = bool(p.get("qa_override", False))

    try:
        _job_print(job.job_id, "PIPELINE INPUT", p)
        await job.emit("job_status", {"status": "running", "message": "Starting pipeline"})

        # Ensure services are up before running.
        status = await ensure_services_running(start_missing=False)
        down = [s for s in status["services"] if not s["running"]]
        await job.emit("services", status)
        if down:
            job.status = "failed"
            job.message = "One or more services are down"
            _job_print(job.job_id, "SERVICES DOWN", down)
            await job.emit("job_status", {"status": job.status, "message": job.message, "down": down})
            return

        results: dict[str, Any] = {"input": {"patient_id": p["patient_id"], "modality": p["modality"]}}
        await job.emit("input", p)

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Stage 1
            qc_url = qc_endpoint_for_modality(p["modality"])
            _job_print(
                job.job_id,
                "STAGE 1 REQUEST (Image QA)",
                {
                    "url": qc_url,
                    "file_name": job.upload_name,
                    "file_size_bytes": len(job.dicom_bytes),
                    "use_gpt_report": False,
                    "qa_override": qa_override,
                },
            )
            await job.emit("stage_start", {"stage": 1, "name": "Image QA", "url": qc_url})
            qc_resp = await client.post(
                qc_url,
                files={"file": (job.upload_name, job.dicom_bytes, job.content_type)},
                data={"use_gpt_report": "false"},
            )
            try:
                qc_json = qc_resp.json()
            except Exception:  # noqa: BLE001
                qc_json = {"raw": qc_resp.text}
            results["stage_1_image_qa"] = {"status_code": qc_resp.status_code, "response": qc_json}

            qc_status = (qc_json or {}).get("qc_status")
            qa_pass = qc_status in {"PASS", "WARNING"}
            results["stage_1_image_qa"]["qa_pass"] = qa_pass
            results["stage_1_image_qa"]["qa_override_used"] = qa_override
            _job_print(job.job_id, "STAGE 1 RESPONSE (Image QA)", results["stage_1_image_qa"])
            await job.emit("stage_result", {"stage": 1, "result": results["stage_1_image_qa"]})

            if not qa_pass:
                results["workflow"] = {
                    "continued_after_stage_1": True,
                    "reason": "QA not PASS/WARNING",
                    "qc_status": qc_status,
                }
                _job_print(job.job_id, "WORKFLOW CONTINUED AFTER QA", results["workflow"])

            # Stage 2
            interp_url = interpretation_endpoint_for_modality(p["modality"])
            _job_print(
                job.job_id,
                "STAGE 2 REQUEST (AI Interpretation)",
                {"url": interp_url, "file_name": job.upload_name, "file_size_bytes": len(job.dicom_bytes)},
            )
            await job.emit("stage_start", {"stage": 2, "name": "AI Interpretation", "url": interp_url})
            interp_resp = await client.post(
                interp_url,
                files={"file": (job.upload_name, job.dicom_bytes, job.content_type)},
            )
            try:
                interp_json = interp_resp.json()
            except Exception:  # noqa: BLE001
                interp_json = {"raw": interp_resp.text}
            results["stage_2_ai_interpretation"] = {"status_code": interp_resp.status_code, "response": interp_json}
            _job_print(job.job_id, "STAGE 2 RESPONSE (AI Interpretation)", results["stage_2_ai_interpretation"])
            await job.emit("stage_result", {"stage": 2, "result": results["stage_2_ai_interpretation"]})

            # Stage 3
            _job_print(
                job.job_id,
                "STAGE 3 REQUEST (Report Correction)",
                {
                    "url": f"{_REPORT}/api/v1/report-correction",
                    "json": {
                        "doctor_notes": p["doctor_notes"],
                        "radiologist_notes": p["radiologist_notes"],
                        "exam_type": p["exam_type"],
                        "extracted_dicom_metadata": {
                            "PatientID": p["patient_id"],
                            "PatientName": p["patient_name"],
                            "OrderID": p["order_id"],
                            "OrderDate": p["order_date"],
                            "DateOfBirth": p["date_of_birth"],
                            "NationalID": p["national_id"],
                            "Gender": p["gender"],
                            "AccessionNumber": p["accession_number"],
                            "Modality": p["modality"],
                            "BodyPartExamined": p["body_part"],
                            "ViewPosition": "PA",
                            "StudyDate": p["study_date"],
                        },
                    },
                },
            )
            await job.emit("stage_start", {"stage": 3, "name": "Report Correction", "url": f"{_REPORT}/api/v1/report-correction"})
            stage3_body = {
                "doctor_notes": p["doctor_notes"],
                "radiologist_notes": p["radiologist_notes"],
                "exam_type": p["exam_type"],
                "extracted_dicom_metadata": {
                    "PatientID": p["patient_id"],
                    "PatientName": p["patient_name"],
                    "OrderID": p["order_id"],
                    "OrderDate": p["order_date"],
                    "DateOfBirth": p["date_of_birth"],
                    "NationalID": p["national_id"],
                    "Gender": p["gender"],
                    "AccessionNumber": p["accession_number"],
                    "Modality": p["modality"],
                    "BodyPartExamined": p["body_part"],
                    "ViewPosition": "PA",
                    "StudyDate": p["study_date"],
                },
            }
            rc_resp = await client.post(f"{_REPORT}/api/v1/report-correction", json=stage3_body)
            try:
                rc_json = rc_resp.json()
            except Exception:  # noqa: BLE001
                rc_json = {"raw": rc_resp.text}
            results["stage_3_report_correction"] = {"status_code": rc_resp.status_code, "response": rc_json}
            rc_sn = rc_json.get("safety_normalized_output") if isinstance(rc_json, dict) else {}
            clinical_report_text = _build_clinical_report_text(
                rc_sn if isinstance(rc_sn, dict) else {},
                doctor_notes=p["doctor_notes"],
                radiologist_notes=p["radiologist_notes"],
            )
            results["stage_3_report_correction"]["clinical_report_text"] = clinical_report_text
            _job_print(job.job_id, "STAGE 3 RESPONSE (Report Correction)", results["stage_3_report_correction"])
            await job.emit("stage_result", {"stage": 3, "result": results["stage_3_report_correction"]})

            # Stage 4
            _job_print(
                job.job_id,
                "STAGE 4 REQUEST (Analysis Matching)",
                {
                    "url": f"{_REPORT}/api/v1/analysis-matching",
                    "json": {
                        "clinical_report": clinical_report_text or "",
                        "ai_image_analysis": {"findings": (interp_json or {}).get("findings", [])},
                        "extracted_dicom_metadata": {
                            "Modality": p["modality"],
                            "ViewPosition": "PA",
                            "StudyDescription": p["exam_type"],
                        },
                    },
                },
            )
            await job.emit("stage_start", {"stage": 4, "name": "Analysis Matching", "url": f"{_REPORT}/api/v1/analysis-matching"})
            stage4_body = {
                "clinical_report": clinical_report_text or "",
                "ai_image_analysis": {"findings": (interp_json or {}).get("findings", [])},
                "extracted_dicom_metadata": {"Modality": p["modality"], "ViewPosition": "PA", "StudyDescription": p["exam_type"]},
            }
            am_resp = await client.post(f"{_REPORT}/api/v1/analysis-matching", json=stage4_body)
            try:
                am_json = am_resp.json()
            except Exception:  # noqa: BLE001
                am_json = {"raw": am_resp.text}
            results["stage_4_analysis_matching"] = {"status_code": am_resp.status_code, "response": am_json}
            _job_print(job.job_id, "STAGE 4 RESPONSE (Analysis Matching)", results["stage_4_analysis_matching"])
            await job.emit("stage_result", {"stage": 4, "result": results["stage_4_analysis_matching"]})

            # Stage 5
            await job.emit("stage_start", {"stage": 5, "name": "Template Autofill", "url": f"{_AUTOFILL}/select-and-fill"})
            sn = am_json.get("safety_normalized_output") if isinstance(am_json, dict) else {}
            reconciled_findings = (sn or {}).get("reconciled_findings", [])
            icd10_codes_raw = (((rc_sn or {}).get("rag_grounding") or {}).get("icd10_codes")) or []
            icd10_codes_str = _as_str_list(icd10_codes_raw)
            input_data = (
                f"Exam: {p['exam_type']}. Patient ID: {p['patient_id']}. "
                f"Clinical report: {clinical_report_text}. "
                f"Reconciled findings: {json.dumps(reconciled_findings)}. "
                f"ICD-10 codes: {', '.join(icd10_codes_str)}."
            )
            stage5_body = {
                "input_data": input_data,
                "patient_context": {
                    "PatientID": p["patient_id"],
                    "PatientName": p["patient_name"],
                    "OrderID": p["order_id"],
                    "AccessionNumber": p["accession_number"],
                    "Gender": p["gender"],
                    "DateOfBirth": p["date_of_birth"],
                    "Modality": p["modality"],
                    "StudyDate": p["study_date"],
                },
                "top_k": 3,
            }
            _job_print(
                job.job_id,
                "STAGE 5 REQUEST (Template Autofill)",
                {"url": f"{_AUTOFILL}/select-and-fill", "json": stage5_body},
            )
            ta_resp = await client.post(f"{_AUTOFILL}/select-and-fill", json=stage5_body)
            try:
                ta_json = ta_resp.json()
            except Exception:  # noqa: BLE001
                ta_json = {"raw": ta_resp.text}
            results["stage_5_template_autofill"] = {"status_code": ta_resp.status_code, "response": ta_json}
            _job_print(job.job_id, "STAGE 5 RESPONSE (Template Autofill)", results["stage_5_template_autofill"])
            await job.emit("stage_result", {"stage": 5, "result": results["stage_5_template_autofill"]})

            missing_fields = (((ta_json.get("autofill") or {}).get("missing_required_fields")) if isinstance(ta_json, dict) else None) or []
            missing_fields_str = _as_str_list(missing_fields)
            critical_alert = bool((interp_json or {}).get("critical_alert", False))
            rendered_report = ((ta_json.get("autofill") or {}).get("rendered_report")) if isinstance(ta_json, dict) else ""
            template_name = ((ta_json.get("selection") or {}).get("selected_template_name")) if isinstance(ta_json, dict) else ""
            template_id = ((ta_json.get("selection") or {}).get("selected_template_id")) if isinstance(ta_json, dict) else ""
            autofill_conf = ((ta_json.get("autofill") or {}).get("confidence_score")) if isinstance(ta_json, dict) else ""
            rc_warnings = ((rc_json.get("safety_normalized_output") or {}).get("warnings")) if isinstance(rc_json, dict) else []
            icd10_str = json.dumps(icd10_codes_raw, ensure_ascii=False)
            warnings_str = json.dumps(rc_warnings, ensure_ascii=False)
            missing_str = ", ".join(missing_fields_str) if missing_fields_str else "None"

            template_text = (
                f"{rendered_report or ''}\n\n"
                f"=== QA SUMMARY ===\n"
                f"QC Status: {qc_status}\n"
                f"Autofill Confidence: {autofill_conf}\n"
                f"Critical AI Alert: {critical_alert}\n\n"
                f"=== ICD-10 CODES ===\n{icd10_str}\n\n"
                f"=== WARNINGS ===\n{warnings_str}\n\n"
                f"=== MISSING FIELDS ===\n{missing_str}\n\n"
                f"DISCLAIMER: AI-assisted draft. Radiologist review required."
            )

            output_record = {
                "ID": template_id,
                "TEMPLATE_NAME": template_name,
                "TEMPLATE_TEXT": template_text,
                "STATUS_ID": None,
                "CREATED_BY": p.get("patient_id") or "",
                "CREATION_DATETIME": None,
                "DELETED_BY": None,
                "DELETE_DATETIME": None,
                "UPDATED_BY": None,
                "UPDATE_DATETIME": None,
                "Physician": p.get("doctor_notes", "")[:120],
                "PatientID": p.get("patient_id") or "",
                "PatientName": p.get("patient_name") or "",
                "OrderID": p.get("order_id") or "",
                "OrderDate": p.get("order_date") or None,
                "DateOfBirth": p.get("date_of_birth") or None,
                "NationalID": p.get("national_id") or "",
                "Gender": p.get("gender") or "",
                "AccessionNumber": p.get("accession_number") or "",
                "qc_status": qc_status,
                "critical_alert": critical_alert,
                "missing_required_fields": missing_fields_str,
            }

            subject_prefix = "🚨 CRITICAL ALERT — Immediate radiologist review required — " if critical_alert else ""
            subject = f"{subject_prefix}[AI DRAFT READY] {p['exam_type']} — Accession {p['accession_number']} — Patient {p['patient_id']}"
            missing_line = f"⚠️ Missing fields: {', '.join(missing_fields_str)}\n\n" if missing_fields_str else ""
            body = (
                "=== REPORT DRAFT (Radiologist review required before finalising) ===\n\n"
                f"{rendered_report or ''}\n\n"
                "=== QA SUMMARY ===\n"
                f"QC Status: {qc_status}\n"
                f"Template Used: {template_name}\n"
                f"Autofill Confidence: {autofill_conf}\n"
                f"Critical AI Alert: {critical_alert}\n\n"
                "=== WARNINGS ===\n"
                f"{json.dumps(rc_warnings, ensure_ascii=False)}\n\n"
                "=== ICD-10 CODES ===\n"
                f"{json.dumps(icd10_codes_raw, ensure_ascii=False)}\n\n"
                f"{missing_line}"
                "DISCLAIMER: This is an AI-assisted draft. Board-certified radiologist review is required before any clinical use.\n"
            )

            results["output_record"] = output_record
            results["summary"] = output_record
            results["delivery_preview"] = {"subject": subject, "body": body}

        job.status = "done"
        job.message = "Done"
        job.result = results
        # Emit final result first so the SSE client can close cleanly after receiving it.
        await job.emit("result", results)
        await job.emit("job_status", {"status": job.status, "message": job.message})
        _job_print(job.job_id, "PIPELINE DONE (Summary)", {"summary": results.get("summary"), "delivery_preview_subject": subject})
    except Exception as e:  # noqa: BLE001
        job.status = "failed"
        job.message = str(e)
        _job_print(job.job_id, "PIPELINE FAILED", {"error": str(e)})
        await job.emit("job_status", {"status": job.status, "message": job.message})
        await job.emit("error", {"message": str(e)})
        return


@app.post("/api/jobs")
async def create_job(
    dicom_file: UploadFile = File(...),
    doctor_notes: str = Form(""),
    radiologist_notes: str = Form(""),
    exam_type: str = Form(""),
    patient_id: str = Form(""),
    patient_name: str = Form(""),
    order_id: str = Form(""),
    order_date: str = Form(""),
    date_of_birth: str = Form(""),
    national_id: str = Form(""),
    gender: str = Form(""),
    accession_number: str = Form(...),
    OutputLanguage: str = Form("el"),
    signing_physician: str = Form(""),
    signing_physician_code: str = Form(""),
    modality: str = Form("CR"),
    body_part: str = Form(""),
    study_date: str = Form(""),
    qa_override: str = Form("false"),
) -> JSONResponse:
    original_bytes = await dicom_file.read()
    original_name = dicom_file.filename or "dicom.zip"
    order_fields = {
        "doctor_notes": doctor_notes,
        "radiologist_notes": radiologist_notes,
        "exam_type": exam_type,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "order_id": order_id,
        "order_date": order_date,
        "date_of_birth": date_of_birth,
        "national_id": national_id,
        "gender": gender,
        "accession_number": accession_number,
        "OutputLanguage": OutputLanguage,
        "signing_physician": signing_physician,
        "signing_physician_code": signing_physician_code,
        "modality": modality,
        "body_part": body_part,
        "study_date": study_date,
        "qa_override": qa_override,
    }
    return await _create_job_from_dicom_bytes(
        original_bytes,
        original_name,
        order_fields,
        content_type=dicom_file.content_type,
    )


@app.post("/api/jobs/from-pacs")
async def create_job_from_pacs(order: PacsOrderInput) -> JSONResponse:
    try:
        dicom_bytes = fetch_dicom_from_pacs(order.AccessionNumber)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return await _create_job_from_dicom_bytes(
        dicom_bytes,
        f"{order.AccessionNumber}.dcm",
        _build_order_fields_from_pacs_input(order),
    )


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def _gen():
        # initial status snapshot
        yield f"event: job_status\ndata: {json.dumps({'status': job.status, 'message': job.message})}\n\n"
        while True:
            item = await job.queue.get()
            event = item.get("event", "message")
            data = item.get("data")
            yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            if event in {"result", "error"}:
                break

    return StreamingResponse(_gen(), media_type="text/event-stream")


@app.post("/api/jobs/{job_id}/resume")
async def resume_job(job_id: str) -> JSONResponse:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "paused":
        return JSONResponse({"job_id": job_id, "status": job.status, "message": "Not paused"})
    # Resume by rerunning with QA override enabled.
    job.payload["qa_override"] = True
    job.status = "running"
    job.message = "Resuming with QA override"
    job.task = asyncio.create_task(_run_pipeline_job(job))
    return JSONResponse({"job_id": job_id, "status": job.status})


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str) -> JSONResponse:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse({"job_id": job.job_id, "status": job.status, "message": job.message})

@app.post("/api/save-draft")
async def api_save_draft(payload: dict[str, Any]) -> JSONResponse:
    patient_id = str(((payload.get("input") or {}).get("patient_id")) or "unknown")
    modality = str(((payload.get("input") or {}).get("modality")) or "unknown")
    stamp = int(time.time())
    safe_name = "".join([c for c in patient_id if c.isalnum() or c in {"-", "_"}])[:64] or "unknown"
    out_path = SAVED_DIR / f"draft_{safe_name}_{modality}_{stamp}.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return JSONResponse({"saved_to": str(out_path)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8090")),
        log_level="info",
    )
