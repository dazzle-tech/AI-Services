from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

from .findings_schema import make_finding
from .models import Finding


_MODEL: Any | None = None
_MODEL_LOAD_ERROR: str | None = None
STRONG_THRESHOLD = 0.60
WEAK_THRESHOLD = 0.35
MODEL_NAME = "torchxrayvision-densenet121-res224-all"

try:
    import torch  # type: ignore
    import torchxrayvision as xrv  # type: ignore

    # Load model once (global)
    _MODEL = xrv.models.DenseNet(weights="densenet121-res224-all")
    _MODEL.eval()
except Exception as e:  # pragma: no cover
    _MODEL = None
    _MODEL_LOAD_ERROR = str(e) or e.__class__.__name__


def _preprocess_image(image_path: str):
    if _MODEL is None:
        raise RuntimeError(f"X-ray model unavailable: {_MODEL_LOAD_ERROR or 'unknown error'}")

    # imported under try: torch/xrv
    import torch  # type: ignore
    import torchxrayvision as xrv  # type: ignore

    img = Image.open(image_path).convert("L")
    img = img.resize((224, 224))
    img = np.asarray(img, dtype=np.float32)

    img = xrv.datasets.normalize(img, 255)
    img = np.expand_dims(img, axis=0)  # (1, H, W)
    img = np.expand_dims(img, axis=0)  # (1, 1, H, W)

    return torch.from_numpy(img).float()


def build_findings_from_model_outputs(model_outputs: dict[str, float]) -> list[Finding]:
    """
    Convert raw TorchXRayVision pathology probabilities into assistive candidate findings.
    This function is pure and testable without requiring the model runtime.
    """
    label_map = {
        "Effusion": "PLEURAL_EFFUSION",
        "Pneumothorax": "PNEUMOTHORAX",
        "Cardiomegaly": "CARDIOMEGALY",
        "Consolidation": "CONSOLIDATION",
        "Lung Opacity": "LUNG_OPACITY",
        "Infiltration": "INFILTRATION",
        "Pneumonia": "PNEUMONIA",
        "Edema": "PULMONARY_EDEMA",
        "Atelectasis": "ATELECTASIS",
    }

    findings: list[Finding] = []
    for label, code in label_map.items():
        prob = float(model_outputs.get(label, 0.0))
        if prob < WEAK_THRESHOLD:
            continue

        confidence_band = "low" if prob < STRONG_THRESHOLD else "standard"
        priority = "ROUTINE"
        if code == "PNEUMOTHORAX" and prob >= STRONG_THRESHOLD:
            priority = "CRITICAL" if prob >= 0.80 else "URGENT"
        elif code == "PLEURAL_EFFUSION" and prob >= STRONG_THRESHOLD:
            priority = "URGENT" if prob >= 0.80 else "ROUTINE"

        if confidence_band == "low":
            finding_text = (
                f"Low-confidence AI candidate {code.lower().replace('_', ' ')}. "
                "Radiologist review required."
            )
        else:
            finding_text = (
                f"Possible {code.lower().replace('_', ' ')}. Radiologist review required."
            )

        findings.append(
            make_finding(
                finding_code=code,
                finding_text=finding_text,
                location="chest",
                confidence=prob,
                priority=priority,
            )
        )

    # Combined lung abnormality rule (weak threshold). Avoid duplicates when strong opacity exists.
    lung_labels = {
        "Lung Opacity",
        "Infiltration",
        "Consolidation",
        "Pneumonia",
        "Atelectasis",
    }
    lung_signal = max([float(model_outputs.get(l, 0.0)) for l in lung_labels] or [0.0])
    has_strong_opacity = any(
        f.finding_code in {"LUNG_OPACITY", "CONSOLIDATION"} and f.confidence >= STRONG_THRESHOLD
        for f in findings
    )
    if (lung_signal >= WEAK_THRESHOLD) and (not has_strong_opacity):
        findings.append(
            make_finding(
                finding_code="POSSIBLE_LUNG_OPACITY_OR_AIRSPACE_ABNORMALITY",
                finding_text=(
                    "Possible low-confidence lung opacity or air-space abnormality. "
                    "Radiologist review required."
                ),
                location="chest",
                confidence=lung_signal,
                priority="ROUTINE",
            )
        )

    return findings


def run_xray_model(
    image_path: str,
    exam_type: str,
) -> tuple[list[Finding], dict[str, float], dict[str, Any]]:
    if not exam_type.startswith("XR_CHEST"):
        return [], {}, {
            "name": MODEL_NAME,
            "strong_threshold": STRONG_THRESHOLD,
            "weak_threshold": WEAK_THRESHOLD,
            "not_for_medical_use": True,
        }

    if _MODEL is None:
        raise RuntimeError(f"X-ray model unavailable: {_MODEL_LOAD_ERROR or 'unknown error'}")

    # imported under try: torch/xrv
    import torch  # type: ignore
    import torchxrayvision as xrv  # type: ignore

    img = _preprocess_image(image_path)

    with torch.no_grad():
        preds = _MODEL(img)[0].detach().cpu().numpy()

    # Raw probabilities for debugging/QA. (Assistive only; radiologist review required.)
    model_outputs: dict[str, float] = {}
    for i, label in enumerate(xrv.datasets.default_pathologies):
        try:
            model_outputs[str(label)] = float(preds[i])
        except Exception:
            continue

    findings = build_findings_from_model_outputs(model_outputs)

    model_meta = {
        "name": MODEL_NAME,
        "strong_threshold": STRONG_THRESHOLD,
        "weak_threshold": WEAK_THRESHOLD,
        "not_for_medical_use": True,
    }
    return findings, model_outputs, model_meta


def gpt_xray_available(api_key: str | None) -> bool:
    return bool(api_key)


def model_status(api_key: str | None = None) -> dict:
    """Return model load status for health checks."""
    status: dict[str, Any] = {"model": MODEL_NAME}
    if _MODEL is not None:
        status.update({"model_loaded": True})
    else:
        status.update({"model_loaded": False, "model_error": _MODEL_LOAD_ERROR or "unknown"})
    status.update({"gpt_xray_available": gpt_xray_available(api_key)})
    return status
