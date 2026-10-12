"""Clinical output generation via OpenAI (SOAP, narrative summary, or document)."""

from typing import Any, Dict, List, Union

from app.ai.client import AIClient
from app.ai.prompts import format_role_tagged_transcript
from app.ai.unified_prompts import (
    TranscriptionRequest,
    as_transcription_request,
    build_system_prompt,
    build_user_prompt,
)
from app.core import config
from app.models.schemas import (
    ClinicalDocument,
    NarrativeSummary,
    SOAPSummary,
    TranscriptionRequestOptions,
)

ClinicalOutput = Union[SOAPSummary, NarrativeSummary, ClinicalDocument]


def summarize_transcript(
    segments: List[dict],
    role_map: Dict[str, str],
    client: AIClient | None = None,
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | None = None,
) -> ClinicalOutput:
    tagged = format_role_tagged_transcript(segments, role_map)
    req = _summary_request(prompt_options)

    if config.settings.use_llm_stub:
        soap_payload = _stub_summarize(segments, role_map)
        payload = _adapt_stub_payload(soap_payload, req.purpose)
    else:
        llm = client or AIClient()
        payload = llm.complete_json(
            model=config.settings.summary_model,
            system_prompt=build_system_prompt(req),
            user_prompt=build_user_prompt(req, tagged),
        )

    return _validate_output(payload, req.purpose)


def _summary_request(
    prompt_options: TranscriptionRequest | TranscriptionRequestOptions | dict | None,
) -> TranscriptionRequest:
    if prompt_options is None:
        base = TranscriptionRequestOptions().to_transcription_request()
    else:
        base = as_transcription_request(prompt_options)
    if base.purpose not in {"summary", "soap_note", "clinical_document"}:
        return base.model_copy(update={"purpose": "soap_note"})
    return base


def _validate_output(payload: Dict[str, Any], purpose: str) -> ClinicalOutput:
    if purpose == "summary":
        return NarrativeSummary.model_validate(payload)
    if purpose == "clinical_document":
        return ClinicalDocument.model_validate(payload)
    return SOAPSummary.model_validate(payload)


def _adapt_stub_payload(soap: Dict[str, Any], purpose: str) -> Dict[str, Any]:
    if purpose == "summary":
        return {
            "summary": soap.get("subjective") or "Not discussed",
            "key_points": [soap["assessment"]] if soap.get("assessment") and soap["assessment"] != "Not discussed" else [],
            "follow_up": soap.get("follow_up") or "Not discussed",
            "flags": soap.get("flags") or [],
        }
    if purpose == "clinical_document":
        return {
            "title": "Clinical visit note",
            "body": soap.get("subjective") or "Not discussed",
            "attendees_listed": ["doctor", "patient"],
            "sections": {
                "subjective": soap.get("subjective", "Not discussed"),
                "objective": soap.get("objective", "Not discussed"),
                "assessment": soap.get("assessment", "Not discussed"),
                "plan": soap.get("plan", "Not discussed"),
            },
            "flags": soap.get("flags") or [],
        }
    return soap


def _stub_summarize(segments: List[dict], role_map: Dict[str, str]) -> Dict[str, Any]:
    """Extract only stated facts — no hallucination in stub mode."""
    patient_lines: List[str] = []
    doctor_lines: List[str] = []

    for segment in segments:
        role = role_map.get(segment["speaker_label"], "other")
        if role == "patient":
            patient_lines.append(segment["text"])
        elif role == "doctor":
            doctor_lines.append(segment["text"])

    patient_text = " ".join(patient_lines)
    doctor_text = " ".join(doctor_lines)

    medications: List[str] = []
    if "acetaminophen" in doctor_text.lower():
        medications.append("acetaminophen as needed")

    assessment = "Not discussed"
    if "viral pharyngitis" in doctor_text.lower():
        assessment = "Likely viral pharyngitis."

    plan = "Not discussed"
    if "rest" in doctor_text.lower() and "fluids" in doctor_text.lower():
        plan = "Rest, fluids, acetaminophen as needed. Follow up if worsening."

    follow_up = "Not discussed"
    if "follow up" in doctor_text.lower():
        follow_up = "Follow up if symptoms worsen."

    flags: List[str] = []
    if "sore throat" in patient_text.lower() and "sore throat" not in doctor_text.lower():
        flags.append("Patient reported sore throat; doctor did not explicitly acknowledge it.")

    return {
        "subjective": patient_text or "Not discussed",
        "objective": doctor_text if any(word in doctor_text.lower() for word in ("examine", "temperature")) else "Not discussed",
        "assessment": assessment,
        "plan": plan,
        "medications_mentioned": medications,
        "follow_up": follow_up,
        "flags": flags,
    }
