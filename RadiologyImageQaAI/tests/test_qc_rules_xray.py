from __future__ import annotations

import datetime as _dt
from pathlib import Path
import shutil
import uuid

import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from app.models import IssueType, MissingRegion, QCStatus
from app.qc_rules_xray import evaluate_xray_qc


def _make_workdir() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp" / "pytest_xray"
    root.mkdir(parents=True, exist_ok=True)
    d = root / uuid.uuid4().hex
    d.mkdir(parents=True, exist_ok=False)
    return d


def _write_dicom(
    path: Path,
    *,
    modality: str = "DX",
    body_part_examined: str = "CHEST",
    view_position: str | None = "PA",
    study_description: str = "CHEST",
    series_description: str | None = None,
    pixel_array: np.ndarray | None = None,
) -> Path:
    file_meta = FileMetaDataset()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(
        str(path),
        {},
        file_meta=file_meta,
        preamble=b"\0" * 128,
    )
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = generate_uid()
    file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    file_meta.ImplementationClassUID = generate_uid()

    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.Modality = modality
    ds.BodyPartExamined = body_part_examined
    if view_position is not None:
        ds.ViewPosition = view_position
    ds.StudyDescription = study_description
    ds.SeriesDescription = series_description or (view_position or "")
    ds.PatientName = "TEST"
    ds.PatientID = "TEST"
    ds.StudyDate = _dt.datetime.now().strftime("%Y%m%d")

    if pixel_array is None:
        pixel_array = np.zeros((64, 64), dtype=np.uint16)
    pixel_array = np.asarray(pixel_array)
    if pixel_array.dtype != np.uint16:
        pixel_array = pixel_array.astype(np.uint16)

    ds.Rows = int(pixel_array.shape[0])
    ds.Columns = int(pixel_array.shape[1])
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelData = pixel_array.tobytes()

    pydicom.dcmwrite(str(path), ds, write_like_original=False)
    return path


def test_single_pa_image_pass() -> None:
    workdir = _make_workdir()
    try:
        rng = np.random.default_rng(0)
        arr = (
            rng.normal(loc=30000, scale=4000, size=(256, 256))
            .clip(0, 65535)
            .astype(np.uint16)
        )
        fp = _write_dicom(workdir / "pa.dcm", view_position="PA", pixel_array=arr)

        res = evaluate_xray_qc(
            metadata={
                "modality": "DX",
                "study_description": "CHEST",
                "series_description": "PA",
                "protocol_name": "CXR",
                "body_part_examined": "CHEST",
                "study_instance_uid": "1.2.3",
                "view_position": "PA",
            },
            dicom_files=[fp],
        )

        assert res["qc_status"] == QCStatus.PASS
        assert res["issue_type"] == IssueType.NO_ISSUE
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_two_view_chest_without_lateral_fail() -> None:
    workdir = _make_workdir()
    try:
        arr = np.full((128, 128), 30000, dtype=np.uint16)
        fp1 = _write_dicom(workdir / "pa.dcm", view_position="PA", pixel_array=arr)
        fp2 = _write_dicom(workdir / "ap.dcm", view_position="AP", pixel_array=arr)

        res = evaluate_xray_qc(
            metadata={
                "modality": "DX",
                "study_description": "CHEST (2 VIEWS)",
                "series_description": "PA",
                "protocol_name": "CHEST 2V",
                "body_part_examined": "CHEST",
                "study_instance_uid": "1.2.3",
                "view_position": "PA",
            },
            dicom_files=[fp1, fp2],
        )

        assert res["qc_status"] == QCStatus.FAIL
        assert res["issue_type"] == IssueType.MISSING_VIEW
        assert res.get("missing_region") == MissingRegion.LATERAL_VIEW
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_missing_viewposition_review_required() -> None:
    workdir = _make_workdir()
    try:
        fp = _write_dicom(
            workdir / "img.dcm",
            view_position=None,
            pixel_array=np.full((64, 64), 30000, dtype=np.uint16),
        )

        res = evaluate_xray_qc(
            metadata={
                "modality": "DX",
                "study_description": "CHEST",
                "series_description": None,
                "protocol_name": None,
                "body_part_examined": "CHEST",
                "study_instance_uid": "1.2.3",
                "view_position": None,
            },
            dicom_files=[fp],
        )

        assert res["qc_status"] == QCStatus.REVIEW_REQUIRED
        assert res["issue_type"] == IssueType.MISSING_METADATA
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def test_overexposed_image_warning() -> None:
    workdir = _make_workdir()
    try:
        arr = np.full((256, 256), 65000, dtype=np.uint16)
        fp = _write_dicom(workdir / "pa.dcm", view_position="PA", pixel_array=arr)

        res = evaluate_xray_qc(
            metadata={
                "modality": "DX",
                "study_description": "CHEST",
                "series_description": "PA",
                "protocol_name": "CXR",
                "body_part_examined": "CHEST",
                "study_instance_uid": "1.2.3",
                "view_position": "PA",
            },
            dicom_files=[fp],
        )

        assert res["qc_status"] == QCStatus.WARNING
        assert res["issue_type"] == IssueType.POOR_EXPOSURE
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
