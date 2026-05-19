from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass(frozen=True)
class LandmarkDetection:
    landmarks: Dict[str, bool]
    confidence: float
    notes: str


def run_totalsegmentator(input_path: str, output_dir: str) -> str:
    """
    Run TotalSegmentator via the current Python interpreter (no PATH/CLI dependency).

    Returns stdout as a string. Raises RuntimeError on failure.
    """
    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "totalsegmentator.bin.TotalSegmentator",
        "-i",
        input_path,
        "-o",
        output_dir,
        "--fast",
    ]

    print("[totalseg] cmd:", cmd)
    proc = subprocess.run(cmd, capture_output=True, text=True)

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if stdout.strip():
        print("[totalseg] stdout:\n", stdout)
    if stderr.strip():
        print("[totalseg] stderr:\n", stderr)

    if proc.returncode != 0:
        raise RuntimeError(
            "TotalSegmentator failed "
            f"(returncode={proc.returncode}). "
            f"cmd={cmd!r}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )

    return stdout


def _mask_exists(output_dir: Path, name: str) -> bool:
    for ext in [".nii.gz", ".nii"]:
        if (output_dir / f"{name}{ext}").exists():
            return True
    return False


def _load_mask_any(output_dir: Path, name: str) -> Path | None:
    for ext in [".nii.gz", ".nii"]:
        p = output_dir / f"{name}{ext}"
        if p.exists():
            return p
    return None


def _z_extent_fraction(mask_path: Path) -> tuple[float, float]:
    """
    Returns (z_min_fraction, z_max_fraction) within [0, 1].
    Best-effort; falls back to (0.0, 0.0) if nibabel isn't available or mask is empty.
    """
    try:
        import nibabel as nib  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return (0.0, 0.0)

    img = nib.load(str(mask_path))
    data = np.asanyarray(img.dataobj)
    if data.ndim < 3:
        return (0.0, 0.0)

    nonzero = np.argwhere(data > 0)
    if nonzero.size == 0:
        return (0.0, 0.0)

    z = nonzero[:, 2]
    z_min = int(z.min())
    z_max = int(z.max())
    z_len = int(data.shape[2])
    if z_len <= 1:
        return (0.0, 0.0)

    return (z_min / (z_len - 1), z_max / (z_len - 1))


def detect_landmarks_from_masks(output_dir: Path) -> LandmarkDetection:
    """
    MVP heuristic landmark detection based on mask existence.
    TODO: Replace with validated landmark localization and z-extent checks.
    """
    landmarks: Dict[str, bool] = {
        # Chest
        "lung_apices_seen": False,
        "lung_bases_seen": False,

        # Head
        "skull_vertex_seen": False,
        "skull_base_seen": False,

        # Abdomen / pelvis
        "diaphragm_or_lung_bases_seen": False,
        "liver_dome_seen": False,
        "kidneys_seen": False,
        "bladder_seen": False,
        "pubic_symphysis_seen": False,
    }
    notes: list[str] = []

    # Lungs (for chest coverage and as diaphragm proxy).
    # Prefer lobes if present (TotalSegmentator "total" task), else fall back to merged lungs.
    lung_paths = [
        _load_mask_any(output_dir, n)
        for n in [
            "lung_upper_lobe_left",
            "lung_lower_lobe_left",
            "lung_upper_lobe_right",
            "lung_middle_lobe_right",
            "lung_lower_lobe_right",
            "lung_left",
            "lung_right",
            "lungs",
        ]
    ]
    lung_paths = [p for p in lung_paths if p]
    if lung_paths:
        apices_ok = False
        bases_ok = False
        for lp in lung_paths:
            zmin_f, zmax_f = _z_extent_fraction(lp)
            if zmax_f >= 0.85:
                apices_ok = True
            if zmin_f <= 0.15:
                bases_ok = True
            if apices_ok and bases_ok:
                break

        landmarks["lung_apices_seen"] = apices_ok
        landmarks["lung_bases_seen"] = bases_ok
        # For abdomen protocols, treat lung bases as a diaphragm proxy.
        landmarks["diaphragm_or_lung_bases_seen"] = bases_ok

        if not apices_ok:
            notes.append("Lung masks present but do not reach superior slices; lung apices uncertain.")
        if not bases_ok:
            notes.append("Lung masks present but do not reach inferior slices; lung bases uncertain.")
    else:
        notes.append("No lung masks found; chest/diaphragm heuristics unavailable.")

    if _mask_exists(output_dir, "liver"):
        landmarks["liver_dome_seen"] = True
    else:
        notes.append("No liver mask found.")

    kidney_left = _mask_exists(output_dir, "kidney_left")
    kidney_right = _mask_exists(output_dir, "kidney_right")
    landmarks["kidneys_seen"] = bool(kidney_left or kidney_right)
    if not landmarks["kidneys_seen"]:
        notes.append("No kidney masks found.")

    if _mask_exists(output_dir, "urinary_bladder") or _mask_exists(output_dir, "bladder"):
        landmarks["bladder_seen"] = True
    else:
        notes.append("No bladder masks found.")

    # Pubic symphysis (inferior coverage proxy):
    pubic_path = _load_mask_any(output_dir, "pubic_bone") or _load_mask_any(output_dir, "pelvis")
    if pubic_path:
        zmin_f, _ = _z_extent_fraction(pubic_path)
        # If pelvis structures reach the inferior portion (~bottom 15%), assume pubic region is covered.
        landmarks["pubic_symphysis_seen"] = zmin_f <= 0.15
        if not landmarks["pubic_symphysis_seen"]:
            notes.append("Pelvis mask present but does not reach inferior slices; pubic symphysis uncertain.")
    else:
        pelvis_proxy_path = _load_mask_any(output_dir, "hip_left") or _load_mask_any(output_dir, "hip_right") or _load_mask_any(output_dir, "sacrum")
        if pelvis_proxy_path:
            zmin_f, _ = _z_extent_fraction(pelvis_proxy_path)
            landmarks["pubic_symphysis_seen"] = zmin_f <= 0.15
            notes.append("Pubic symphysis approximated from pelvis proxies (hip/sacrum). Low confidence.")
        else:
            notes.append("No pelvis proxies found for pubic symphysis approximation.")

    # Head (best-effort): use brain mask if present as a proxy for head coverage.
    brain_path = _load_mask_any(output_dir, "brain")
    if brain_path:
        zmin_f, zmax_f = _z_extent_fraction(brain_path)
        landmarks["skull_vertex_seen"] = zmax_f >= 0.85
        landmarks["skull_base_seen"] = zmin_f <= 0.15
        if not landmarks["skull_vertex_seen"]:
            notes.append("Brain mask present but limited superior z-extent; skull vertex uncertain.")
        if not landmarks["skull_base_seen"]:
            notes.append("Brain mask present but limited inferior z-extent; skull base uncertain.")
    else:
        notes.append("No brain mask found; head coverage heuristics unavailable.")

    confidence = 0.7
    if any("Low confidence" in n for n in notes):
        confidence = 0.6
    if not notes:
        confidence = 0.75

    return LandmarkDetection(landmarks=landmarks, confidence=confidence, notes="; ".join(notes))
