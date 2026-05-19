"""Clinician-support (advice-style) flow.

This flow is NOT treatment advice. It produces a grounded patient summary and
review points based only on retrieved patient data, keyed by MRN.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple, List

from app.infrastructure.llm.llm_client import get_llm_client
from app.services.mrn import extract_mrn
from app.services.patient_record import PatientRecordService, PatientRecord

logger = logging.getLogger(__name__)


_STRONG_ADVICE_HINTS = [
    "advice",
    "what should we do",
    "what do we do",
    "recommend",
    "recommendation",
    "next steps",
    "next step",
    "management",
    "manage",
    "plan for",
]

_WEAK_ADVICE_HINTS = [
    "what to do",
    "what do i do",
    "what should i do",
]


def is_advice_style_question(text: str) -> bool:
    tl = (text or "").strip().lower()
    if not tl:
        return False
    mrn_in_text = ("mrn" in tl) or (extract_mrn(text, allow_standalone=True) is not None)
    patient_ref = mrn_in_text or ("patient" in tl)

    # Strong advice hints can be classified as advice when there's a patient reference
    # (MRN or an explicit "patient" mention). Missing MRN triggers a safe refusal downstream.
    if any(h in tl for h in _STRONG_ADVICE_HINTS):
        return patient_ref

    # Weak advice hints are ambiguous; require an MRN reference to avoid hijacking general data queries.
    if any(h in tl for h in _WEAK_ADVICE_HINTS):
        return mrn_in_text

    return False


_BLOCK_PHRASES = [
    "diagnosis:",
    "the patient has",
    "prescribe",
    "treat with",
    "increase dose",
    "decrease dose",
]
_BLOCK_WORDS = [
    "start",
    "stop",
]


def validate_advice_output(text: str) -> Tuple[bool, Optional[str]]:
    """Return (ok, error) for clinician-support output constraints."""
    tl = (text or "").lower()
    if not tl.strip():
        return False, "Empty clinician-support output."

    for phrase in _BLOCK_PHRASES:
        if phrase in tl:
            return False, f"Blocked phrase detected: {phrase!r}"

    for word in _BLOCK_WORDS:
        if re.search(rf"\\b{re.escape(word)}\\b", tl):
            return False, f"Blocked word detected: {word!r}"

    return True, None


def _format_list(items: List[str]) -> str:
    items = [i for i in (items or []) if i not in (None, "", "null", "undefined")]
    return ", ".join(items) if items else "—"


def build_fallback_response(record: PatientRecord) -> str:
    """Deterministic safe response if the model output is blocked."""
    demos = record.demographics or {}

    # Avoid forbidden wording such as "the patient has" and "diagnosis:".
    lines = []
    lines.append("Patient Summary")
    lines.append(f"- MRN: {record.mrn}")
    if demos.get("full_name"):
        lines.append(f"- Name: {demos.get('full_name')}")
    if demos.get("date_of_birth"):
        lines.append(f"- Date of birth: {demos.get('date_of_birth')}")
    if demos.get("sex_at_birth"):
        lines.append(f"- Sex at birth: {demos.get('sex_at_birth')}")

    lines.append("")
    lines.append("Notable Findings")
    if record.vitals:
        lines.append(f"- Recent vitals entries: {len(record.vitals)}")
    else:
        lines.append("- Recent vitals entries: —")
    if record.labs:
        flagged = [x for x in record.labs if str(x.get("marker") or "").strip()]
        lines.append(f"- Recent lab results: {len(record.labs)} (flagged entries: {len(flagged)})")
    else:
        lines.append("- Recent lab results: —")

    lines.append("")
    lines.append("Missing Information")
    missing = []
    if not record.vitals:
        missing.append("vitals")
    if not record.labs:
        missing.append("labs")
    if not record.medications:
        missing.append("medications")
    if not record.allergies:
        missing.append("allergies")
    if not record.visit_history:
        missing.append("visit history")
    if not record.diagnoses:
        missing.append("charted diagnoses")
    lines.append(f"- Missing or unavailable sections: {_format_list(missing)}")

    lines.append("")
    lines.append("Clinician Review Points")
    lines.append("- Review the chart for medication reconciliation, allergies, and recent clinical notes.")
    lines.append("- Verify recent labs and vital sign trends in the EHR.")

    lines.append("")
    lines.append("Safety Flags")
    if record.labs:
        markers = sorted({str(x.get('marker')).strip() for x in record.labs if str(x.get('marker') or '').strip()})
        lines.append(f"- Lab result markers present in record: {_format_list(markers)}")
    else:
        lines.append("- No lab result markers available in the retrieved record.")

    return "\n".join(lines).strip()


def _json_default(obj: Any) -> Any:  # pragma: no cover
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


class ClinicianAdviceService:
    """End-to-end clinician-support flow keyed by MRN."""

    def __init__(
        self,
        *,
        patient_record_service: Optional[PatientRecordService] = None,
        llm_client: Optional[Any] = None,
    ):
        self.patient_record_service = patient_record_service or PatientRecordService()
        self.llm_client = llm_client or get_llm_client()

    def handle_advice_request(self, *, user_id: str, message: str) -> Dict[str, Any]:
        mrn = extract_mrn(message, allow_standalone=True)
        if not mrn:
            return {
                "intent": "advice",
                "text": "Please include a Medical Record Number (MRN), for example: 'MRN P104'.",
                "data_json": {"type": "summary", "count": 0},
                "meta": {"error": "missing_mrn"},
            }

        record = self.patient_record_service.get_patient_record_by_mrn(user_id, mrn)
        if not record:
            return {
                "intent": "advice",
                "text": f"No accessible patient record found for MRN {mrn}.",
                "data_json": {"type": "summary", "count": 0},
                "meta": {"error": "patient_not_found", "mrn": mrn},
            }

        patient_context = asdict(record)
        # Grounded-only prompt: no free-text medical advice; reason strictly over retrieved data.
        prompt = (
            "You are a clinician-support assistant. Use ONLY the patient context JSON below.\n"
            "Do NOT invent diagnoses.\n"
            "Do NOT prescribe treatment.\n"
            "Do NOT propose medication changes.\n"
            "Output ONLY these sections (in this order):\n"
            "1) Patient Summary\n"
            "2) Notable Findings\n"
            "3) Missing Information\n"
            "4) Clinician Review Points\n"
            "5) Safety Flags\n"
            "\n"
            "Hard constraints:\n"
            "- Do not write 'diagnosis:'\n"
            "- Do not write 'the patient has'\n"
            "- Do not use words 'start' or 'stop'\n"
            "- Do not use phrases 'increase dose', 'decrease dose', 'prescribe', or 'treat with'\n"
            "\n"
            f"Patient context JSON:\n{json.dumps(patient_context, ensure_ascii=False, indent=2, default=_json_default)}\n"
        )

        reply = (self.llm_client.generate(prompt, options={"temperature": 0.0, "max_tokens": 900}) or "").strip()
        ok, err = validate_advice_output(reply)
        if not ok:
            logger.warning("Blocked clinician-support output for MRN=%s: %s", record.mrn, err)
            reply = build_fallback_response(record)

        return {
            "intent": "advice",
            "text": reply,
            "data_json": {"type": "summary", "count": 0},
            "meta": {"mrn": record.mrn},
        }
