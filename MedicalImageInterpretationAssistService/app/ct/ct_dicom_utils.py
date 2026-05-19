from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pydicom
from PIL import Image


def safe_extract_zip(zip_path: Path, out_dir: Path) -> None:
    """Extract zip with path traversal protection."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        resolved_base = out_dir.resolve()
        for member in zf.namelist():
            target = (out_dir / member).resolve()
            if not str(target).startswith(str(resolved_base)):
                raise ValueError(f"Unsafe zip entry (path traversal): {member}")
        zf.extractall(out_dir)


def find_dicom_files(root: Path) -> list[Path]:
    files = []
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if p.suffix.lower() in {".dcm", ""}:
            files.append(p)
    return files


def _first_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
            value = list(value)[0]
        return float(value)
    except Exception:
        return None


def build_series_index(dicom_files: list[Path]) -> list[dict[str, Any]]:
    """
    Group DICOM files by SeriesInstanceUID and return one metadata dict per series
    with the associated file list.
    """
    series_map: dict[str, dict[str, Any]] = {}
    files_map: dict[str, list[Path]] = {}

    for fp in dicom_files:
        try:
            ds = pydicom.dcmread(str(fp), stop_before_pixels=True, force=True)
        except Exception:
            continue

        series_uid = str(getattr(ds, "SeriesInstanceUID", "") or "").strip() or "UNKNOWN_SERIES"
        files_map.setdefault(series_uid, []).append(fp)

        if series_uid in series_map:
            continue

        def g(attr: str) -> str | None:
            v = getattr(ds, attr, None)
            return str(v).strip() or None if v else None

        series_map[series_uid] = {
            "series_instance_uid": series_uid,
            "study_description": g("StudyDescription"),
            "series_description": g("SeriesDescription"),
            "body_part_examined": g("BodyPartExamined"),
            "protocol_name": g("ProtocolName"),
            "window_center": _first_float(getattr(ds, "WindowCenter", None)),
            "window_width": _first_float(getattr(ds, "WindowWidth", None)),
            "convolution_kernel": g("ConvolutionKernel"),
            "image_type": g("ImageType"),
            "slice_thickness": _first_float(getattr(ds, "SliceThickness", None)),
        }

    out: list[dict[str, Any]] = []
    for series_uid, meta in series_map.items():
        out.append({"meta": meta, "files": files_map.get(series_uid, [])})
    return out


def extract_ct_metadata(dicom_files: list[Path]) -> dict[str, Any]:
    """Read metadata from first readable DICOM file."""
    for fp in dicom_files:
        try:
            ds = pydicom.dcmread(str(fp), stop_before_pixels=True, force=True)

            def g(attr: str) -> str | None:
                v = getattr(ds, attr, None)
                return str(v).strip() or None if v else None

            return {
                "modality": g("Modality"),
                "study_description": g("StudyDescription"),
                "series_description": g("SeriesDescription"),
                "body_part_examined": g("BodyPartExamined"),
                "protocol_name": g("ProtocolName"),
                "study_instance_uid": g("StudyInstanceUID"),
                "patient_position": g("PatientPosition"),
                "contrast_bolus_agent": g("ContrastBolusAgent"),
                "slice_thickness": g("SliceThickness"),
                "kvp": g("KVP"),
                "window_center": _first_float(getattr(ds, "WindowCenter", None)),
                "window_width": _first_float(getattr(ds, "WindowWidth", None)),
                "convolution_kernel": g("ConvolutionKernel"),
                "image_type": g("ImageType"),
                "slice_count": None,  # filled below
            }
        except Exception:
            continue
    return {k: None for k in ["modality", "study_description", "series_description",
                               "body_part_examined", "protocol_name", "study_instance_uid",
                               "patient_position", "contrast_bolus_agent", "slice_thickness",
                               "kvp", "slice_count"]}


def dicom_slice_to_png(dicom_path: Path, output_path: Path, window_center: float | None = None, window_width: float | None = None) -> None:
    """
    Convert a single CT DICOM slice to a windowed PNG.
    Default windowing: soft tissue (WC=40, WW=400).
    """
    ds = pydicom.dcmread(str(dicom_path), force=True)
    if not hasattr(ds, "pixel_array"):
        raise RuntimeError("DICOM has no pixel data")

    arr = np.asarray(ds.pixel_array, dtype=np.float32)
    if arr.ndim > 2:
        arr = arr[0]

    # Apply rescale
    slope = float(getattr(ds, "RescaleSlope", 1.0) or 1.0)
    intercept = float(getattr(ds, "RescaleIntercept", 0.0) or 0.0)
    arr = arr * slope + intercept  # now in HU

    # Windowing
    wc = window_center if window_center is not None else float(getattr(ds, "WindowCenter", 40) or 40)
    ww = window_width if window_width is not None else float(getattr(ds, "WindowWidth", 400) or 400)
    # Handle DICOM sequences
    if hasattr(wc, "__iter__"):
        wc = float(list(wc)[0])
    if hasattr(ww, "__iter__"):
        ww = float(list(ww)[0])

    lo = wc - ww / 2
    hi = wc + ww / 2
    arr = np.clip(arr, lo, hi)
    arr = ((arr - lo) / (hi - lo) * 255).astype(np.uint8)

    Image.fromarray(arr).save(str(output_path))


def select_representative_slices(dicom_files: list[Path], max_slices: int = 6) -> list[Path]:
    """
    Sort CT slices by InstanceNumber or filename, then pick evenly-spaced
    representative slices (avoiding first and last 10% which are often outside ROI).
    Returns up to max_slices paths.
    """
    def sort_key(p: Path):
        try:
            ds = pydicom.dcmread(str(p), stop_before_pixels=True, force=True)
            return int(getattr(ds, "InstanceNumber", 0) or 0)
        except Exception:
            return 0

    sorted_files = sorted(dicom_files, key=sort_key)
    n = len(sorted_files)
    if n == 0:
        return []
    if n <= max_slices:
        return sorted_files

    # Skip first and last 10%
    skip = max(1, n // 10)
    usable = sorted_files[skip: n - skip]
    if not usable:
        usable = sorted_files

    # Evenly spaced
    indices = [int(i * (len(usable) - 1) / (max_slices - 1)) for i in range(max_slices)]
    return [usable[i] for i in indices]
