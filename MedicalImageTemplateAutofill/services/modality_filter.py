from __future__ import annotations

from typing import Any


def normalize_modality(value: Any) -> str:
    return str(value or "").strip().upper()


def allowed_modalities_for_context(modality: Any) -> set[str]:
    mod = normalize_modality(modality)
    if not mod:
        return set()
    if mod in {"CR", "DX"}:
        return {"CR", "DX"}
    return {mod}


def filter_templates(templates: list[Any], patient_context: dict[str, Any] | None) -> list[Any]:
    ctx = patient_context or {}
    mod = ctx.get("modality_filter") or ctx.get("Modality") or ctx.get("modality")
    allowed = allowed_modalities_for_context(mod)
    if not allowed:
        return list(templates)

    out: list[Any] = []
    for t in templates:
        tmod = None
        if isinstance(t, dict):
            tmod = t.get("modality") or t.get("Modality")
        else:
            tmod = getattr(t, "modality", None)
        if normalize_modality(tmod) in allowed:
            out.append(t)
    return out

