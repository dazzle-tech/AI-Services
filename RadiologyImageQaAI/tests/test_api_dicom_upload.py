from __future__ import annotations

import io
import zipfile
from typing import Any

import pytest
from fastapi.testclient import TestClient


def _make_zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture()
def client() -> TestClient:
    # Import inside fixture so monkeypatching app.main is easy per-test.
    from main import app

    return TestClient(app)


def test_qc_dicom_requires_multipart_file(client: TestClient) -> None:
    # Missing `file` field should raise FastAPI validation error.
    resp = client.post("/api/v1/qc/ct/dicom")
    assert resp.status_code == 422


def test_qc_dicom_accepts_zip_and_returns_review_required_for_unknown_protocol(
    client: TestClient,
) -> None:
    # Even if the content isn't a valid DICOM, the endpoint should accept the ZIP
    # and respond with a structured QCResult (not 422).
    zip_bytes = _make_zip_bytes({"study/0001.dcm": b"NOT_A_REAL_DICOM"})

    resp = client.post(
        "/api/v1/qc/ct/dicom",
        files={"file": ("study.zip", zip_bytes, "application/zip")},
    )

    assert resp.status_code == 200
    payload: dict[str, Any] = resp.json()

    # With no metadata / unknown protocol in this environment, the service returns REVIEW_REQUIRED.
    assert payload["qc_status"] == "REVIEW_REQUIRED"
    assert payload["human_review_required"] is True
    assert payload["disclaimer"]


def test_qc_dicom_ct_ap_happy_path_pass_with_stubbed_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # This is an end-to-end HTTP test while stubbing external tools:
    # - dicom2nifti (not installed in CI/dev by default)
    # - TotalSegmentator CLI
    # We still exercise request parsing, temp workdir creation, rule logic, and response shaping.
    from app.dicom_utils import DICOMMetadata
    from app.segmentation import LandmarkDetection
    import app.main as service

    def fake_read_metadata(_dicom_files):
        return DICOMMetadata(
            study_instance_uid="1.2.3",
            study_description="CT Abdomen Pelvis",
            series_description="CT ABD PELVIS",
            protocol_name="CT A/P",
            body_part_examined="ABDOMEN",
            modality="CT",
            view_position=None,
        )

    def fake_convert(_dicom_root, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        dummy = out_dir / "dummy.nii.gz"
        dummy.write_bytes(b"nifti-placeholder")
        return dummy

    def fake_totalseg(_nifti_path, _seg_dir):
        # No-op: we stub landmark detection directly.
        return None

    def fake_detect(_seg_dir):
        return LandmarkDetection(
            landmarks={
                "diaphragm_or_lung_bases_seen": True,
                "liver_dome_seen": True,
                "kidneys_seen": True,
                "bladder_seen": True,
                "pubic_symphysis_seen": True,
            },
            confidence=0.75,
            notes="stubbed",
        )

    monkeypatch.setattr(service, "read_metadata", fake_read_metadata)
    monkeypatch.setattr(service, "_convert_dicom_to_nifti", fake_convert)
    monkeypatch.setattr(service, "run_totalsegmentator", fake_totalseg)
    monkeypatch.setattr(service, "detect_landmarks_from_masks", fake_detect)

    from main import app

    client = TestClient(app)
    zip_bytes = _make_zip_bytes({"study/0001.dcm": b"ANY"})

    resp = client.post(
        "/api/v1/qc/ct/dicom",
        files={"file": ("study.zip", zip_bytes, "application/zip")},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["exam_type"] == "CT_ABDOMEN_PELVIS"
    assert payload["qc_status"] == "PASS"
    assert payload["issue_type"] == "NO_ISSUE"
    assert payload["details"]["source"] == "totalsegmentator_masks"
    assert "QC REVIEW REQUIRED" not in payload["explanation"]


def test_qc_dicom_ct_abdomen_notes_filtered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.dicom_utils import DICOMMetadata
    from app.segmentation import LandmarkDetection
    import app.main as service

    def fake_read_metadata(_dicom_files):
        return DICOMMetadata(
            study_instance_uid="1.2.3",
            study_description="CT Abdomen",
            series_description="ABD",
            protocol_name="CT ABD",
            body_part_examined="ABDOMEN",
            modality="CT",
            view_position=None,
        )

    def fake_convert(_dicom_root, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        dummy = out_dir / "dummy.nii.gz"
        dummy.write_bytes(b"nifti-placeholder")
        return dummy

    def fake_totalseg(_in_path, _out_dir):
        return ""

    def fake_detect(_seg_dir):
        # Intentionally include notes irrelevant to CT_ABDOMEN.
        return LandmarkDetection(
            landmarks={
                "diaphragm_or_lung_bases_seen": True,
                "liver_dome_seen": True,
                "kidneys_seen": True,
                "lung_apices_seen": False,
                "lung_bases_seen": True,
                "pubic_symphysis_seen": False,
                "skull_vertex_seen": False,
                "skull_base_seen": False,
                "bladder_seen": False,
            },
            confidence=0.75,
            notes="No pelvis proxies found for pubic symphysis approximation. No brain mask found; head coverage heuristics unavailable. No kidney masks found. No liver mask found.",
        )

    monkeypatch.setattr(service, "read_metadata", fake_read_metadata)
    monkeypatch.setattr(service, "_convert_dicom_to_nifti", fake_convert)
    monkeypatch.setattr(service, "run_totalsegmentator", fake_totalseg)
    monkeypatch.setattr(service, "detect_landmarks_from_masks", fake_detect)

    from main import app

    client = TestClient(app)
    zip_bytes = _make_zip_bytes({"study/0001.dcm": b"ANY"})
    resp = client.post(
        "/api/v1/qc/ct/dicom",
        files={"file": ("study.zip", zip_bytes, "application/zip")},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["exam_type"] == "CT_ABDOMEN"
    notes = payload["details"].get("notes") or ""
    assert "pubic" not in notes.lower()
    assert "brain" not in notes.lower()
    assert "skull" not in notes.lower()


def test_qc_xray_accepts_single_dicom_file_upload_and_runs_qc(client: TestClient) -> None:
    import datetime as _dt

    import numpy as np
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    def _make_dicom_bytes(*, view_position: str) -> bytes:
        file_meta = FileMetaDataset()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

        ds = FileDataset(
            None,
            {},
            file_meta=file_meta,
            preamble=b"\0" * 128,
        )
        ds.is_little_endian = True
        ds.is_implicit_VR = False

        ds.SOPClassUID = generate_uid()
        ds.SOPInstanceUID = generate_uid()
        file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
        file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
        file_meta.ImplementationClassUID = generate_uid()
        ds.StudyInstanceUID = generate_uid()
        ds.SeriesInstanceUID = generate_uid()
        ds.Modality = "DX"
        ds.BodyPartExamined = "CHEST"
        ds.ViewPosition = view_position
        ds.StudyDescription = "CHEST"
        ds.SeriesDescription = view_position
        ds.PatientName = "TEST"
        ds.PatientID = "TEST"
        ds.StudyDate = _dt.datetime.now().strftime("%Y%m%d")

        rows, cols = 256, 256
        rng = np.random.default_rng(0)
        arr = rng.normal(loc=30000, scale=4000, size=(rows, cols)).clip(0, 65535).astype(np.uint16)
        ds.Rows = rows
        ds.Columns = cols
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated = 16
        ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 0
        ds.PixelData = arr.tobytes()

        buf = io.BytesIO()
        pydicom.dcmwrite(buf, ds, write_like_original=False)
        return buf.getvalue()

    dicom_bytes = _make_dicom_bytes(view_position="PA")
    resp = client.post(
        "/api/v1/qc/xray/dicom",
        files={"file": ("image.dcm", dicom_bytes, "application/dicom")},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["exam_type"] == "XR_CHEST_PA"
    assert payload["qc_status"] == "PASS"
    assert payload["issue_type"] == "NO_ISSUE"
