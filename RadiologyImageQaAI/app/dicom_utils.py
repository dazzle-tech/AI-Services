from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List


@dataclass(frozen=True)
class DICOMMetadata:
    study_instance_uid: str | None
    study_description: str | None
    series_description: str | None
    protocol_name: str | None
    body_part_examined: str | None
    modality: str | None
    view_position: str | None


def extract_zip(zip_path: Path, out_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(out_dir)


def find_dicom_files(root: Path) -> List[Path]:
    # MVP: treat any file without an extension or with .dcm as candidate
    candidates: List[Path] = []
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        ext = p.suffix.lower()
        if ext in {".dcm", ""}:
            candidates.append(p)
    return candidates


def extract_dicom_metadata(folder_path: str) -> dict[str, str | None]:
    """
    Walks a folder, attempts to read each file as DICOM (force=True),
    scores each file by metadata quality, and returns the BEST candidate
    (instead of the first readable one).

    Debug output is printed to help diagnose real-world DICOM oddities.
    """
    try:
        import pydicom  # type: ignore
    except Exception as e:
        print(f"[dicom] pydicom import failed: {e}")
        return {
            "modality": None,
            "study_description": None,
            "series_description": None,
            "body_part_examined": None,
            "protocol_name": None,
            "study_instance_uid": None,
            "view_position": None,
        }

    root = Path(folder_path)
    if not root.exists():
        print(f"[dicom] folder does not exist: {root}")
        return {
            "modality": None,
            "study_description": None,
            "series_description": None,
            "body_part_examined": None,
            "protocol_name": None,
            "study_instance_uid": None,
            "view_position": None,
        }

    # Loop through all files; keep candidates and select the highest-scoring one.
    candidates: list[tuple[int, str, dict[str, str | None]]] = []

    def _score(md: dict[str, str | None]) -> int:
        score = 0
        mod = (md.get("modality") or "").strip().upper()
        if mod == "CT":
            score += 3
        elif mod in {"CR", "DX", "XR", "RG"}:
            score += 2
        elif mod:
            score += 1
        if md.get("series_description"):
            score += 2
        if md.get("study_description"):
            score += 2
        if md.get("body_part_examined"):
            score += 1
        return score

    for fp in root.rglob("*"):
        if fp.is_dir():
            continue
        try:
            print(f"[dicom] reading: {fp}")
            ds = pydicom.dcmread(str(fp), stop_before_pixels=True, force=True)

            def _get_str(name: str) -> str | None:
                v: Any = getattr(ds, name, None)
                if v is None:
                    return None
                s = str(v).strip()
                return s or None

            modality = _get_str("Modality")
            study_description = _get_str("StudyDescription")
            series_description = _get_str("SeriesDescription")
            body_part_examined = _get_str("BodyPartExamined")
            protocol_name = _get_str("ProtocolName")
            study_instance_uid = _get_str("StudyInstanceUID")
            view_position = _get_str("ViewPosition")

            md = {
                "modality": modality,
                "study_description": study_description,
                "series_description": series_description,
                "body_part_examined": body_part_examined,
                "protocol_name": protocol_name,
                "study_instance_uid": study_instance_uid,
                "view_position": view_position,
            }

            score = _score(md)
            print(
                "[dicom] score:",
                {
                    "score": score,
                    "path": str(fp),
                    "modality": modality,
                    "study_description": study_description,
                    "series_description": series_description,
                    "body_part_examined": body_part_examined,
                    "view_position": view_position,
                },
            )

            # Keep only candidates with some metadata signal.
            if any([modality, study_description, series_description, body_part_examined, protocol_name]):
                candidates.append((score, str(fp), md))
        except Exception as e:
            print(f"[dicom] skip (not readable as DICOM): {fp} ({e})")
            continue

    if candidates:
        # Highest score wins; tie-break by path for determinism.
        candidates.sort(key=lambda t: (t[0], t[1]))
        best_score, best_path, best_md = candidates[-1]
        print("[dicom] best candidate:", {"score": best_score, "path": best_path})
        return best_md

    print(f"[dicom] no readable DICOM metadata found in: {root}")
    return {
        "modality": None,
        "study_description": None,
        "series_description": None,
        "body_part_examined": None,
        "protocol_name": None,
        "study_instance_uid": None,
        "view_position": None,
    }


def read_metadata(dicom_files: Iterable[Path]) -> DICOMMetadata:
    """
    Reads lightweight metadata (no pixels) from the first readable DICOM.
    Prefer `extract_dicom_metadata` when you have a folder path.
    """
    try:
        import pydicom  # type: ignore
    except Exception:
        return DICOMMetadata(None, None, None, None, None, None, None)

    for fp in dicom_files:
        try:
            ds = pydicom.dcmread(str(fp), stop_before_pixels=True, force=True)
            return DICOMMetadata(
                study_instance_uid=str(getattr(ds, "StudyInstanceUID", None)) if getattr(ds, "StudyInstanceUID", None) else None,
                study_description=str(getattr(ds, "StudyDescription", None)) if getattr(ds, "StudyDescription", None) else None,
                series_description=str(getattr(ds, "SeriesDescription", None)) if getattr(ds, "SeriesDescription", None) else None,
                protocol_name=str(getattr(ds, "ProtocolName", None)) if getattr(ds, "ProtocolName", None) else None,
                body_part_examined=str(getattr(ds, "BodyPartExamined", None)) if getattr(ds, "BodyPartExamined", None) else None,
                modality=str(getattr(ds, "Modality", None)) if getattr(ds, "Modality", None) else None,
                view_position=str(getattr(ds, "ViewPosition", None)) if getattr(ds, "ViewPosition", None) else None,
            )
        except Exception:
            continue

    return DICOMMetadata(None, None, None, None, None, None, None)
