"""Focused tests for DICOM/order mismatch helpers in the workflow."""
import asyncio
import importlib.util
from pathlib import Path
import sys

import httpx
from fastapi.responses import JSONResponse


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "main.py"
SPEC = importlib.util.spec_from_file_location("radiology_workflow_main", MODULE_PATH)
assert SPEC and SPEC.loader
workflow_main = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = workflow_main
SPEC.loader.exec_module(workflow_main)


async def _request(
    method: str,
    path: str,
    *,
    json: dict[str, object] | None = None,
    data: dict[str, object] | None = None,
    files: dict[str, tuple[str, bytes, str]] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=workflow_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, json=json, data=data, files=files)


def _set_pacs_defaults(monkeypatch) -> None:
    monkeypatch.setattr(workflow_main, "PACS_PROTOCOL", "dicomweb")
    monkeypatch.setattr(workflow_main, "PACS_BASE_URL", None)
    monkeypatch.setattr(workflow_main, "PACS_AUTH_TOKEN", None)
    monkeypatch.setattr(workflow_main, "PACS_USERNAME", None)
    monkeypatch.setattr(workflow_main, "PACS_PASSWORD", None)
    monkeypatch.setattr(workflow_main, "PACS_HOST", None)
    monkeypatch.setattr(workflow_main, "PACS_PORT", 104)
    monkeypatch.setattr(workflow_main, "PACS_AE_TITLE", "RADIOLOGY_WORKFLOW")
    monkeypatch.setattr(workflow_main, "PACS_REMOTE_AE_TITLE", "PACS")
    monkeypatch.setattr(workflow_main, "PACS_MOVE_DESTINATION_AE", None)
    monkeypatch.setattr(workflow_main, "PACS_TIMEOUT_SECONDS", 30.0)
    monkeypatch.setattr(workflow_main, "PACS_ENABLED", False)


def test_build_dicom_order_mismatch_context_flags_cross_study_mismatch():
    context = workflow_main._build_dicom_order_mismatch_context(
        {
            "accession_number": "ACC-10015",
            "study_instance_uid": "1.2.840.10008.1.2.3.15",
        },
        order_accession="ACC-10008",
        radiologist_notes=(
            "Previous study reviewed under accession ACC-10008. "
            "StudyInstanceUID=1.2.840.10008.1.2.3.8"
        ),
        order_metadata={"AccessionNumber": "ACC-10008", "StudyInstanceUID": "1.2.840.10008.1.2.3.8"},
    )

    assert context["dicom_order_mismatch"] is True
    assert context["dicom_order_mismatch_warning"] == workflow_main._DICOM_ORDER_MISMATCH_WARNING
    assert context["DICOMAccessionNumber"] == "ACC-10015"
    assert context["StudyInstanceUID"] == "1.2.840.10008.1.2.3.15"
    assert context["dicom_order_mismatch_reasons"]


def test_build_dicom_order_mismatch_context_stays_clean_for_same_study():
    context = workflow_main._build_dicom_order_mismatch_context(
        {
            "accession_number": "ACC-10008",
            "study_instance_uid": "1.2.840.10008.1.2.3.8",
        },
        order_accession="ACC-10008",
        radiologist_notes="Comparison study StudyInstanceUID=1.2.840.10008.1.2.3.8",
        order_metadata={"AccessionNumber": "ACC-10008", "StudyInstanceUID": "1.2.840.10008.1.2.3.8"},
    )

    assert context["dicom_order_mismatch"] is False
    assert context["dicom_order_mismatch_warning"] is None
    assert context["dicom_order_mismatch_reasons"] is None


def test_build_delivery_preview_prefixes_subject_when_mismatch_warning_exists():
    preview = workflow_main._build_delivery_preview(
        {"TEMPLATE_TEXT": "report", "TEMPLATE_NAME": "RADIOLOGY REPORT"},
        exam_type="Chest X-ray",
        accession_number="ACC-10015",
        patient_id="P123",
        qc_status="PASS",
        dicom_order_mismatch_warning=workflow_main._DICOM_ORDER_MISMATCH_WARNING,
    )

    assert preview["subject"].startswith(workflow_main._DICOM_ORDER_MISMATCH_SUBJECT_PREFIX)
    assert "report" in preview["body"]


def test_api_status_includes_pacs_readiness(monkeypatch):
    _set_pacs_defaults(monkeypatch)

    async def fake_ensure_services_running(start_missing: bool) -> dict[str, object]:
        return {"services": [{"name": "stub", "running": True}]}

    monkeypatch.setattr(workflow_main, "ensure_services_running", fake_ensure_services_running)

    response = asyncio.run(_request("GET", "/api/status"))

    assert response.status_code == 200
    body = response.json()
    assert body["pacs"] == {
        "pacs_enabled": False,
        "pacs_protocol": "dicomweb",
        "pacs_configured": False,
        "missing_settings": ["PACS_BASE_URL"],
    }


def test_create_job_from_pacs_returns_503_when_pacs_is_disabled(monkeypatch):
    _set_pacs_defaults(monkeypatch)
    response = asyncio.run(_request("POST", "/api/jobs/from-pacs", json={"AccessionNumber": "ACC-10008"}))

    assert response.status_code == 503
    assert "PACS_ENABLED=true" in response.json()["detail"]


def test_create_job_from_pacs_requires_accession_number():
    response = asyncio.run(_request("POST", "/api/jobs/from-pacs", json={}))

    assert response.status_code == 422


def test_create_job_from_pacs_returns_501_when_dicomweb_is_enabled_but_not_implemented(monkeypatch):
    _set_pacs_defaults(monkeypatch)
    monkeypatch.setattr(workflow_main, "PACS_ENABLED", True)
    monkeypatch.setattr(workflow_main, "PACS_BASE_URL", "https://pacs.example.local/dicomweb")

    response = asyncio.run(_request("POST", "/api/jobs/from-pacs", json={"AccessionNumber": "ACC-10008"}))

    assert response.status_code == 501
    assert "DICOMweb WADO-RS retrieval not yet implemented" in response.json()["detail"]
    assert "https://pacs.example.local/dicomweb" in response.json()["detail"]


def test_create_job_from_pacs_reuses_shared_job_creation_helper(monkeypatch):
    captured: dict[str, object] = {}

    def fake_fetch_dicom_from_pacs(accession_number: str) -> bytes:
        captured["accession_number"] = accession_number
        return b"stub-dicom"

    async def fake_create_job_from_dicom_bytes(
        dicom_bytes: bytes,
        upload_name: str,
        order_fields: dict[str, object],
        *,
        content_type: str | None = None,
    ) -> JSONResponse:
        captured["dicom_bytes"] = dicom_bytes
        captured["upload_name"] = upload_name
        captured["order_fields"] = order_fields
        captured["content_type"] = content_type
        return JSONResponse({"job_id": "pacs-job-1"})

    monkeypatch.setattr(workflow_main, "fetch_dicom_from_pacs", fake_fetch_dicom_from_pacs)
    monkeypatch.setattr(workflow_main, "_create_job_from_dicom_bytes", fake_create_job_from_dicom_bytes)

    response = asyncio.run(
        _request(
            "POST",
            "/api/jobs/from-pacs",
            json={
                "PatientID": "P123",
                "PatientName": "Alex Example",
                "OrderID": "ORD-77",
                "OrderDate": "2026-06-10T12:30:00",
                "DateOfBirth": "1988-01-05T00:00:00",
                "NationalID": "999999999",
                "Gender": "M",
                "AccessionNumber": "ACC-10008",
                "OutputLanguage": "en",
                "signing_physician": "Dr Test",
                "signing_physician_code": "MD-7",
                "doctor_notes": "Needs comparison",
                "radiologist_notes": "Prior reviewed",
                "exam_type": "Chest X-ray",
                "qa_override": True,
            },
        )
    )

    assert response.status_code == 200
    assert response.json() == {"job_id": "pacs-job-1"}
    assert captured["accession_number"] == "ACC-10008"
    assert captured["dicom_bytes"] == b"stub-dicom"
    assert captured["upload_name"] == "ACC-10008.dcm"
    assert captured["content_type"] is None
    assert captured["order_fields"] == {
        "doctor_notes": "Needs comparison",
        "radiologist_notes": "Prior reviewed",
        "exam_type": "Chest X-ray",
        "patient_id": "P123",
        "patient_name": "Alex Example",
        "order_id": "ORD-77",
        "order_date": "2026-06-10T12:30:00",
        "date_of_birth": "1988-01-05T00:00:00",
        "national_id": "999999999",
        "gender": "M",
        "accession_number": "ACC-10008",
        "OutputLanguage": "en",
        "signing_physician": "Dr Test",
        "signing_physician_code": "MD-7",
        "modality": "",
        "body_part": "",
        "study_date": "",
        "qa_override": True,
    }


def test_create_job_upload_route_reuses_shared_job_creation_helper(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_create_job_from_dicom_bytes(
        dicom_bytes: bytes,
        upload_name: str,
        order_fields: dict[str, object],
        *,
        content_type: str | None = None,
    ) -> JSONResponse:
        captured["dicom_bytes"] = dicom_bytes
        captured["upload_name"] = upload_name
        captured["order_fields"] = order_fields
        captured["content_type"] = content_type
        return JSONResponse({"job_id": "upload-job-1"})

    monkeypatch.setattr(workflow_main, "_create_job_from_dicom_bytes", fake_create_job_from_dicom_bytes)

    response = asyncio.run(
        _request(
            "POST",
            "/api/jobs",
            files={"dicom_file": ("study.dcm", b"fake-dicom", "application/dicom")},
            data={
                "accession_number": "ACC-UP-1",
                "patient_id": "P-UP-1",
                "qa_override": "true",
            },
        )
    )

    assert response.status_code == 200
    assert response.json() == {"job_id": "upload-job-1"}
    assert captured["dicom_bytes"] == b"fake-dicom"
    assert captured["upload_name"] == "study.dcm"
    assert captured["content_type"] == "application/dicom"
    assert captured["order_fields"]["accession_number"] == "ACC-UP-1"
    assert captured["order_fields"]["patient_id"] == "P-UP-1"
    assert captured["order_fields"]["qa_override"] == "true"
