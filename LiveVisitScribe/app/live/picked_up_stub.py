"""Deterministic picked-up list for USE_LLM_STUB=true. Keyword rules over the final segments."""

from __future__ import annotations

import re
from typing import Any, Optional

from app.live.text_utils import is_question_only, sentences
from app.models.schemas import PatientContext, Segment

_SYMPTOM_RE = re.compile(
    r"\b(?:headache|nausea|aura|pain|fever|cough|dizz\w*|vomiting|rash|fatigue|shortness of breath|"
    r"sore throat|vision|صداع|غثيان|ألم)\b",
    re.IGNORECASE,
)
_COMPLAINT_RE = re.compile(r"\b(?:i have|i've|i had|my|عندي)\b", re.IGNORECASE)
_EXAM_RE = re.compile(
    r"\b(?:blood pressure|bp|pulse|temperature|oxygen saturation|respiratory rate|neuro(?:logical)?|"
    r"papilloedema|papilledema|weight|height)\b",
    re.IGNORECASE,
)
_FINDING_RE = re.compile(r"\d|\b(?:normal|abnormal|clear|tender|swollen|red)\b", re.IGNORECASE)
_DRUGS = (
    "neurofen", "ibuprofen", "paracetamol", "acetaminophen", "propranolol", "lisinopril", "amoxicillin",
    "azithromycin", "aspirin", "metformin", "sumatriptan", "omeprazole", "amlodipine",
)
_DOSE_RE = re.compile(
    r"\b(?:about |around |roughly )?(?:\d+(?:[.,]\d+)?|one|two|three|four|five|six)\s*"
    r"(?:mg|mcg|g|ml|tablets?|pills?|capsules?|puffs?|drops?)"
    r"(?:\s+(?:once |twice |\d+ times )?(?:a|per|each|every) (?:day|night|morning|week)"
    r"|\s+(?:daily|twice daily|once daily|at night))?",
    re.IGNORECASE,
)


_LEAD = r"\s*(?:is|of|was|:)?\s*"
_BP_RE = re.compile(rf"\b(?:blood pressure|bp){_LEAD}(\d+)\s*(?:over|/)\s*(\d+)", re.IGNORECASE)
_RECORD_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("vital_sign", "heartRate", re.compile(rf"\b(?:pulse|heart rate){_LEAD}(\d+)", re.IGNORECASE)),
    ("vital_sign", "temperature", re.compile(rf"\btemperature{_LEAD}(\d+(?:\.\d+)?)", re.IGNORECASE)),
    ("vital_sign", "oxygenSaturation", re.compile(rf"\b(?:oxygen saturation|spo2){_LEAD}(\d+)", re.IGNORECASE)),
    ("vital_sign", "respiratoryRate", re.compile(rf"\brespiratory rate{_LEAD}(\d+)", re.IGNORECASE)),
    ("body_measurements", "weight", re.compile(rf"\bweight{_LEAD}(\d+(?:\.\d+)?)\s*(?:kg|kilo)", re.IGNORECASE)),
    ("body_measurements", "height", re.compile(rf"\bheight{_LEAD}(\d+(?:\.\d+)?)\s*(?:cm|centimet)", re.IGNORECASE)),
    (
        "pain_assessment",
        "painLevel",
        re.compile(rf"\bpain(?: score| level)?{_LEAD}(\d+)\s*(?:out of|/)\s*10", re.IGNORECASE),
    ),
)


def _stub_record(segments: list[Segment]) -> dict[str, Any]:
    """Spoken vitals, measurements and a pain score by keyword. First mention of a field wins."""
    record: dict[str, dict[str, Any]] = {}

    def put(group: str, name: str, value: str, seg_id: str) -> None:
        record.setdefault(group, {}).setdefault(name, {"value": value, "segment_ids": [seg_id]})

    for segment in segments:
        if is_question_only(segment.text):
            continue
        bp = _BP_RE.search(segment.text)
        if bp:
            put("vital_sign", "bloodPressureSystolic", bp.group(1), segment.id)
            put("vital_sign", "bloodPressureDiastolic", bp.group(2), segment.id)
        for group, name, pattern in _RECORD_RULES:
            match = pattern.search(segment.text)
            if match:
                put(group, name, match.group(1), segment.id)
    return record


def _clean(sentence: str) -> str:
    return sentence.strip().rstrip(".!؟?").strip()


def stub_picked_up(segments: list[Segment], context: Optional[PatientContext]) -> dict[str, Any]:
    complaint: Optional[dict[str, Any]] = None
    symptoms: list[dict[str, Any]] = []
    exam: list[dict[str, Any]] = []
    seen: set[str] = set()

    for segment in segments:
        for sentence in sentences(segment.text):
            if sentence.endswith(("?", "؟")):
                continue
            text = _clean(sentence)
            key = text.lower()
            if key in seen:
                continue
            if _EXAM_RE.search(text) and _FINDING_RE.search(text):
                seen.add(key)
                exam.append({"text": text, "segment_ids": [segment.id]})
            elif _SYMPTOM_RE.search(text):
                seen.add(key)
                if complaint is None and _COMPLAINT_RE.search(text):
                    complaint = {"text": text, "segment_ids": [segment.id]}
                else:
                    symptoms.append({"text": text, "segment_ids": [segment.id]})

    return {
        "complaint": complaint,
        "symptoms": symptoms,
        "medications": _medications(segments),
        "exam": exam,
        "record": _stub_record(segments),
    }


def _medications(segments: list[Segment]) -> list[dict[str, Any]]:
    medications: list[dict[str, Any]] = []
    named: set[str] = set()
    for index, segment in enumerate(segments):
        for drug in _DRUGS:
            match = re.search(re.escape(drug), segment.text, re.IGNORECASE)
            if not match or drug in named:
                continue
            ids = [segment.id]
            detail: Optional[str] = None
            for offset in range(3):  # the same line, or the answer in the next two
                if index + offset >= len(segments):
                    break
                dose = _DOSE_RE.search(segments[index + offset].text)
                if dose:
                    detail = dose.group(0).strip()
                    if offset:
                        ids.append(segments[index + offset].id)
                    break
            if detail is None and is_question_only(segment.text):
                continue  # "Do you take Neurofen?" alone says nothing about this visit
            named.add(drug)
            medications.append({"name": match.group(0), "detail": detail, "segment_ids": ids})
    return medications
