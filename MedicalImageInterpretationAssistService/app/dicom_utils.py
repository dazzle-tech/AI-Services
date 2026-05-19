from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any


def extract_zip(zip_path: Path, out_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(out_dir)


def find_dicom_files(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if p.suffix.lower() in {".dcm", ""}:
            candidates.append(p)
    return candidates


def _normalize_laterality(raw: str | None) -> str | None:
    if not raw:
        return None
    v = raw.strip().upper()
    if v == "R":
        return "RIGHT"
    if v == "L":
        return "LEFT"
    return v or None


def extract_dicom_metadata(folder_path: str) -> dict[str, str | None]:
    try:
        import pydicom  # type: ignore
    except Exception:
        return {
            "modality": None,
            "study_description": None,
            "series_description": None,
            "body_part_examined": None,
            "protocol_name": None,
            "study_instance_uid": None,
            "view_position": None,
            "performed_protocol_codes": None,
            "image_laterality": None,
            "patient_age": None,
            "patient_sex": None,
        }

    root = Path(folder_path)
    if not root.exists():
        return {
            "modality": None,
            "study_description": None,
            "series_description": None,
            "body_part_examined": None,
            "protocol_name": None,
            "study_instance_uid": None,
            "view_position": None,
            "performed_protocol_codes": None,
            "image_laterality": None,
            "patient_age": None,
            "patient_sex": None,
        }

    best_score = -1
    best_meta: dict[str, str | None] = {
        "modality": None,
        "study_description": None,
        "series_description": None,
        "body_part_examined": None,
        "protocol_name": None,
        "study_instance_uid": None,
        "view_position": None,
        "performed_protocol_codes": None,
        "image_laterality": None,
        "patient_age": None,
        "patient_sex": None,
    }

    def score(md: dict[str, str | None]) -> int:
        s = 0
        if md.get("study_description"):
            s += 2
        if md.get("series_description"):
            s += 2
        if md.get("protocol_name"):
            s += 1
        if md.get("body_part_examined"):
            s += 1
        if md.get("view_position"):
            s += 1
        return s

    for fp in root.rglob("*"):
        if fp.is_dir():
            continue
        try:
            ds = pydicom.dcmread(str(fp), stop_before_pixels=True, force=True)
        except Exception:
            continue

        def get_value(name: str) -> str | None:
            v: Any = getattr(ds, name, None)
            if v is None:
                return None
            text = str(v).strip()
            return text or None

        md = {
            "modality": get_value("Modality"),
            "study_description": get_value("StudyDescription"),
            "series_description": get_value("SeriesDescription"),
            "body_part_examined": get_value("BodyPartExamined"),
            "protocol_name": get_value("ProtocolName"),
            "study_instance_uid": get_value("StudyInstanceUID"),
            "view_position": get_value("ViewPosition"),
            "performed_protocol_codes": None,
            "image_laterality": _normalize_laterality(get_value("ImageLaterality")),
            "patient_age": get_value("PatientAge"),
            "patient_sex": get_value("PatientSex"),
        }

        try:
            seq: Any = getattr(ds, "PerformedProtocolCodeSequence", None)
            if seq:
                meanings: list[str] = []
                for item in seq:
                    meaning = getattr(item, "CodeMeaning", None)
                    if meaning:
                        meanings.append(str(meaning).strip())
                md["performed_protocol_codes"] = "; ".join([m for m in meanings if m]) or None
        except Exception:
            pass
        current_score = score(md)
        if current_score > best_score:
            best_score = current_score
            best_meta = md

    return best_meta
