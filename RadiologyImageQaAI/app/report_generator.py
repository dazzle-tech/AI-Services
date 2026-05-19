from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict

from .config import Settings
from .models import QCStatus


def _enum_value(v: Any) -> Any:
    if isinstance(v, Enum):
        return v.value
    return v


def _template_explanation(qc_result: Dict[str, Any], style: str) -> str:
    status = _enum_value(qc_result.get("qc_status", QCStatus.REVIEW_REQUIRED))
    status = str(status)
    missing_region = _enum_value(qc_result.get("missing_region"))
    landmark = _enum_value(qc_result.get("required_landmark_not_seen"))
    recommended = str(qc_result.get("recommended_action", "") or "").strip()

    # Explanations must match qc_status and stay protocol-agnostic (coverage check only).
    if status == QCStatus.PASS.value:
        return "QC PASS: Required anatomical coverage appears adequate. No immediate action required."

    if status == QCStatus.WARNING.value:
        parts = [f"QC WARNING: Potential coverage issue related to {landmark}."]
        if recommended:
            parts.append(f"Recommended action: {recommended}")
        return " ".join(parts)
    if status == QCStatus.FAIL.value:
        parts = [f"QC FAIL: Anatomical coverage appears incomplete in {missing_region}."]
        if landmark:
            parts.append(f"Missing/uncertain landmark: {landmark}.")
        if recommended:
            parts.append(f"Recommended action: {recommended}")
        return " ".join(parts)

    # REVIEW_REQUIRED (or any unknown)
    parts = ["QC REVIEW REQUIRED: Automatic QC was unavailable or inconclusive; human review is required."]
    if recommended:
        parts.append(f"Recommended action: {recommended}")
    return " ".join(parts)


def generate_explanation(qc_result: Dict[str, Any], *, style: str, settings: Settings) -> str:
    """
    Generates a human-readable QC explanation.
    This MUST NOT be diagnostic. Only technical/coverage QC.
    """
    return _template_explanation(qc_result, style)


def generate_explanation_with_openai(
    qc_result: Dict[str, Any],
    *,
    style: str,
    settings: Settings,
) -> str:
    """
    Optional: Use OpenAI Responses API for phrasing only (never for coverage detection).
    This function is intentionally isolated and safe-fails to deterministic templates.
    """
    if not settings.openai_enabled or not settings.openai_api_key:
        return _template_explanation(qc_result, style)

    if settings.deidentify_before_gpt:
        # The service should not send PHI. Keep only the structured QC summary.
        qc_payload = {
            k: qc_result.get(k)
            for k in [
                "exam_type",
                "qc_status",
                "issue_type",
                "missing_region",
                "required_landmark_not_seen",
                "confidence",
                "recommended_action",
                "human_review_required",
            ]
        }
    else:
        qc_payload = qc_result

    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return _template_explanation(qc_result, style)

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = (
        "You are generating a radiology technical quality-control alert for a CT study.\n"
        "Do NOT diagnose. Do NOT suggest clinical interpretations.\n"
        "Explain the QC result clearly for a CT technologist. Keep it concise.\n"
        f"Style: {style}\n"
        f"Structured QC JSON:\n{json.dumps(qc_payload, indent=2)}\n"
    )

    try:
        resp = client.responses.create(
            model=settings.openai_model,
            input=prompt,
        )
        text = getattr(resp, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        return _template_explanation(qc_result, style)
    except Exception:
        return _template_explanation(qc_result, style)
