from __future__ import annotations

import re

from .models import ExamType


_WS_RE = re.compile(r"\s+")


def _norm(text: str) -> str:
    text = text or ""
    text = text.lower()
    text = text.replace("\\", " ")
    text = text.replace("/", " ")
    text = text.replace("-", " ")
    text = _WS_RE.sub(" ", text).strip()
    return text


def classify_exam_type(
    *fields: str | None,
    modality: str | None = None,
    study_description: str | None = None,
    series_description: str | None = None,
    protocol_name: str | None = None,
    body_part_examined: str | None = None,
    view_position: str | None = None,
) -> ExamType:
    """
    Protocol classifier.

    New (preferred) path:
      - If `modality == "CT"`, classify using BOTH `study_description` and `series_description`.
      - Detect:
          - ("abd" AND "pelvis") -> CT_ABDOMEN_PELVIS
          - ("lung" OR "chest")  -> CT_CHEST
          - otherwise            -> UNKNOWN

    Backward-compatibility path:
      - If only `*fields` are provided, fall back to the older heuristic patterns.
    """
    if (
        modality is not None
        or study_description is not None
        or series_description is not None
        or protocol_name is not None
        or body_part_examined is not None
        or view_position is not None
    ):
        mod = (modality or "").strip().upper()
        # X-ray: CR/DX. Classify as XRAY then refine chest variants.
        if mod in {"CR", "DX"}:
            t = _norm(
                " ".join(
                    [
                        s
                        for s in [
                            study_description,
                            series_description,
                            protocol_name,
                            body_part_examined,
                        ]
                        if s
                    ]
                )
            )

            body = (body_part_examined or "").strip().upper()
            is_chest = (body == "CHEST") or ("chest" in t)
            if not is_chest:
                return ExamType.XRAY_UNKNOWN

            vp = (view_position or "").strip().upper()
            if vp == "PA":
                return ExamType.XR_CHEST_PA
            if vp == "AP":
                return ExamType.XR_CHEST_AP
            if vp in {"LATERAL", "LAT"}:
                return ExamType.XR_CHEST_LATERAL
            return ExamType.XR_CHEST

        # Some systems may label radiography as XR/RG without view tags.
        if mod in {"XR", "RG"}:
            return ExamType.XRAY
        if mod != "CT":
            return ExamType.UNKNOWN

        t = _norm(
            " ".join(
                [
                    s
                    for s in [
                        study_description,
                        series_description,
                        protocol_name,
                        body_part_examined,
                    ]
                    if s
                ]
            )
        )

        has_chest = any(k in t for k in ["chest", "lung", "thorax"])
        has_head = any(k in t for k in ["head", "brain", "skull"])
        has_abd = "abd" in t or "abdomen" in t
        has_pelvis = "pelvis" in t or "a/p" in t or "ap " in f"{t} "

        # Prefer the most specific multi-region first.
        if has_chest and has_abd and has_pelvis:
            return ExamType.CT_CHEST_ABDOMEN_PELVIS
        if has_abd and has_pelvis:
            return ExamType.CT_ABDOMEN_PELVIS
        if has_abd and not has_pelvis:
            return ExamType.CT_ABDOMEN
        if has_head:
            return ExamType.CT_HEAD
        if has_chest:
            return ExamType.CT_CHEST
        return ExamType.UNKNOWN

    combined = " ".join([f for f in fields if f])
    t = _norm(combined)

    xray_patterns = [
        "xray",
        "x ray",
        "x-ray",
        "radiograph",
        "xr ",
        " xr",
        "cxr",
    ]
    if any(p in t for p in xray_patterns):
        return ExamType.XRAY

    ap_patterns = [
        "ct abdomen pelvis",
        "ct abdomen and pelvis",
        "abdomen and pelvis",
        "abd pelvis",
        "abdomen pelvis",
        "ct a p",
        "ct ap",
        "ct a/p",
        "a/p",
    ]
    if any(p in t for p in ap_patterns):
        return ExamType.CT_ABDOMEN_PELVIS
    if "ct chest" in t or "chest ct" in t or "thorax" in t:
        return ExamType.CT_CHEST
    if "ct head" in t or "head ct" in t or "brain" in t:
        return ExamType.CT_HEAD
    if "mri lumbar" in t or ("lumbar" in t and "mri" in t):
        return ExamType.MRI_LUMBAR_SPINE
    return ExamType.UNKNOWN
