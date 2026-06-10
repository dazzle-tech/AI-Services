from __future__ import annotations

import io
import zipfile
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _client():
    from main import app
    return TestClient(app)


def test_ct_health_endpoint() -> None:
    response = _client().get("/api/v1/radiology/ct-interpretation/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ct_endpoint_returns_review_required_without_api_key(monkeypatch) -> None:
    import app.ct.ct_service as svc
    monkeypatch.setattr(svc, "run_gpt_ct_model", lambda **_: (_ for _ in ()).throw(AssertionError("should not be called")))

    from app.config import get_settings, Settings
    monkeypatch.setattr("app.config.get_settings", lambda: Settings(openai_api_key=None))

    # Send a dummy zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("slice.dcm", b"NOTDICOM")
    response = _client().post(
        "/api/v1/radiology/ct-interpretation/dicom",
        files={"file": ("study.zip", buf.getvalue(), "application/zip")},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REVIEW_REQUIRED"
    assert "OPENAI_API_KEY" in response.json()["summary"]


def test_ct_endpoint_unsupported_modality(monkeypatch) -> None:
    import app.ct.ct_service as svc

    monkeypatch.setattr(svc, "extract_ct_metadata", lambda _: {
        "modality": "MR", "study_description": None, "series_description": None,
        "body_part_examined": "BRAIN", "protocol_name": None,
        "study_instance_uid": "1.2.3", "patient_position": None,
        "contrast_bolus_agent": None, "slice_thickness": None, "kvp": None, "slice_count": 1,
    })
    monkeypatch.setattr(svc, "find_dicom_files", lambda _: [Path("/fake/slice.dcm")])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("slice.dcm", b"FAKE")

    from app.config import Settings
    from unittest.mock import patch
    with patch("app.config.get_settings", return_value=Settings(openai_api_key="sk-test")):
        response = _client().post(
            "/api/v1/radiology/ct-interpretation/dicom",
            files={"file": ("study.zip", buf.getvalue(), "application/zip")},
        )
    assert response.json()["status"] == "UNSUPPORTED_MODALITY"


def test_ct_gpt_model_called_and_returns_completed(monkeypatch) -> None:
    import app.ct.ct_service as svc
    from app.interpretation.models import Finding

    stub_finding = Finding(
        finding_code="PULMONARY_NODULE",
        finding_text="Possible pulmonary nodule right upper lobe. Radiologist review required.",
        location="right upper lobe",
        confidence=0.72,
        priority="ROUTINE",
        radiologist_review_required=True,
    )

    monkeypatch.setattr(svc, "extract_ct_metadata", lambda _: {
        "modality": "CT", "study_description": "CT CHEST", "series_description": "AXIAL",
        "body_part_examined": "CHEST", "protocol_name": None,
        "study_instance_uid": "1.2.99", "patient_position": None,
        "contrast_bolus_agent": None, "slice_thickness": "1.5", "kvp": "120", "slice_count": 80,
    })
    monkeypatch.setattr(svc, "find_dicom_files", lambda _: [Path("/fake/1.dcm")] * 10)
    monkeypatch.setattr(svc, "select_representative_slices", lambda files, max_slices: files[:2])
    monkeypatch.setattr(svc, "dicom_slice_to_png", lambda src, dst: dst.write_bytes(b"PNG"))
    monkeypatch.setattr(svc, "run_gpt_ct_model", lambda **kwargs: (
        [stub_finding],
        {"body_part": "CHEST", "findings": []},
        {"name": "gpt-4o-ct-vision", "body_part_detected": "CHEST", "image_quality": "ADEQUATE", "view_detected": "AXIAL"},
    ))

    from app.config import Settings
    from unittest.mock import patch
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("1.dcm", b"FAKE")
    with patch("app.config.get_settings", return_value=Settings(openai_api_key="sk-test")):
        response = _client().post(
            "/api/v1/radiology/ct-interpretation/dicom",
            files={"file": ("ct.zip", buf.getvalue(), "application/zip")},
        )
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["exam_type"] == "CT_CHEST"
    assert any(f["finding_code"] == "PULMONARY_NODULE" for f in body["findings"])
    assert body["ai"]["model_name"] == "gpt-4o-ct-vision"
    assert body["ai"]["modality_handled"] == "CT"
    assert body["study"]["modality"] == "CT"
    assert "Radiologist review required" in body["disclaimer"]


def test_ct_abdomen_lung_window_series_flags_mismatch_and_suppresses_chest_findings(monkeypatch) -> None:
    import app.ct.ct_service as svc
    from app.interpretation.models import Finding

    # Study labeled abdomen, but series is lung window
    monkeypatch.setattr(svc, "extract_ct_metadata", lambda _: {
        "modality": "CT",
        "study_description": "CT ABDOMEN W&W/O CONT",
        "series_description": "Lung 5.0 PV PHASE CE",
        "body_part_examined": "ABDOMEN",
        "protocol_name": "CT ABDOMEN",
        "study_instance_uid": "1.2.123",
        "patient_position": None,
        "contrast_bolus_agent": None,
        "slice_thickness": "5.0",
        "kvp": "120",
        "slice_count": 10,
        "window_center": -550,
        "window_width": 1600,
        "convolution_kernel": "B70f",
        "image_type": None,
    })
    monkeypatch.setattr(svc, "find_dicom_files", lambda _: [Path("/fake/1.dcm")] * 10)
    monkeypatch.setattr(svc, "build_series_index", lambda files: [{
        "meta": {
            "study_description": "CT ABDOMEN W&W/O CONT",
            "series_description": "Lung 5.0 PV PHASE CE",
            "body_part_examined": "ABDOMEN",
            "protocol_name": "CT ABDOMEN",
            "window_center": -550,
            "window_width": 1600,
            "convolution_kernel": "B70f",
            "image_type": None,
            "slice_thickness": 5.0,
        },
        "files": files,
    }])
    monkeypatch.setattr(svc, "select_representative_slices", lambda files, max_slices: files[:2])
    monkeypatch.setattr(svc, "dicom_slice_to_png", lambda src, dst: dst.write_bytes(b"PNG"))

    chest_finding = Finding(
        finding_code="PULMONARY_NODULE",
        finding_text="Possible pulmonary nodule. Radiologist review required.",
        location="right lower lobe",
        confidence=0.7,
        priority="ROUTINE",
        radiologist_review_required=True,
    )

    monkeypatch.setattr(
        svc,
        "run_gpt_ct_model",
        lambda **kwargs: (
            [chest_finding],
            {"body_part": "CHEST", "findings": []},
            {"name": "gpt-4o-ct-vision", "body_part_detected": "CHEST", "image_quality": "ADEQUATE", "view_detected": "AXIAL"},
        ),
    )

    from app.config import Settings
    from unittest.mock import patch
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("1.dcm", b"FAKE")
    with patch("app.config.get_settings", return_value=Settings(openai_api_key="sk-test")):
        response = _client().post(
            "/api/v1/radiology/ct-interpretation/dicom",
            files={"file": ("ct.zip", buf.getvalue(), "application/zip")},
        )
    body = response.json()
    assert body["exam_type"] == "CT_ABDOMEN"
    assert body["status"] == "REVIEW_REQUIRED"
    assert body["study"]["body_part"] == "ABDOMEN"
    assert body["findings"] == []
    assert body["warnings"]


def test_ct_endpoint_accepts_output_language_and_localizes_human_text(monkeypatch) -> None:
    import app.ct.ct_service as svc
    from app.interpretation.models import Finding

    stub_finding = Finding(
        finding_code="PULMONARY_NODULE",
        finding_text="Possible pulmonary nodule right upper lobe. Radiologist review required.",
        location="right upper lobe",
        confidence=0.72,
        priority="ROUTINE",
        radiologist_review_required=True,
    )

    monkeypatch.setattr(svc, "extract_ct_metadata", lambda _: {
        "modality": "CT", "study_description": "CT CHEST", "series_description": "AXIAL",
        "body_part_examined": "CHEST", "protocol_name": None,
        "study_instance_uid": "1.2.99", "patient_position": None,
        "contrast_bolus_agent": None, "slice_thickness": "1.5", "kvp": "120", "slice_count": 80,
    })
    monkeypatch.setattr(svc, "find_dicom_files", lambda _: [Path("/fake/1.dcm")] * 10)
    monkeypatch.setattr(svc, "select_representative_slices", lambda files, max_slices: files[:2])
    monkeypatch.setattr(svc, "dicom_slice_to_png", lambda src, dst: dst.write_bytes(b"PNG"))
    monkeypatch.setattr(svc, "run_gpt_ct_model", lambda **kwargs: (
        [stub_finding],
        {"body_part": "CHEST", "findings": []},
        {"name": "gpt-4o-ct-vision", "body_part_detected": "CHEST", "image_quality": "ADEQUATE", "view_detected": "AXIAL"},
    ))

    from app.config import Settings
    from unittest.mock import patch

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("1.dcm", b"FAKE")
    with patch("app.config.get_settings", return_value=Settings(openai_api_key="sk-test")):
        response = _client().post(
            "/api/v1/radiology/ct-interpretation/dicom",
            files={"file": ("ct.zip", buf.getvalue(), "application/zip")},
            data={"OutputLanguage": "el"},
        )
    body = response.json()
    assert response.status_code == 200
    assert "OutputLanguage" not in body
    assert body["findings"][0]["finding_code"] == "PULMONARY_NODULE"
    assert "Απαιτείται αξιολόγηση" in body["findings"][0]["finding_text"]
    assert "Εντοπίστηκε" in body["summary"] or "πιθανά ευρήματα" in body["summary"]
