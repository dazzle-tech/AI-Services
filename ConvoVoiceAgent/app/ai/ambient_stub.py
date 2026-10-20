"""Deterministic draft for USE_LLM_STUB=true.

Keyword rules over the transcript, no network. Output has the same raw shape the note model returns,
so the same evidence rules run on both. Text is copied from segments verbatim (no translation).
"""

from __future__ import annotations

import math
import re
from typing import Any

from app.clinical import icd10

_HEDGES = ("possible", "possibly", "maybe", "might", "probably", "likely", "not sure", "unsure", "i think",
           "ربما", "يمكن", "محتمل", "مش متأكد", "غير متأكد")
_EXAM = ("on examination", "examination", "exam shows", "auscultation", "chest is clear", "lungs are",
         "throat is", "tonsils are", "abdomen is", "tender", "blood pressure is", "temperature is",
         "pulse is", "heart sounds", "بالفحص", "الفحص")
_ROS_SYSTEMS = (
    ("Constitutional", ("fever", "chills", "weight loss", "حرارة", "حمى")),
    ("Respiratory", ("cough", "shortness of breath", "wheez", "سعال", "كحة", "ضيق تنفس")),
    ("Cardiovascular", ("chest pain", "palpitation", "ألم في الصدر", "خفقان")),
    ("Gastrointestinal", ("vomit", "nausea", "diarrh", "constipat", "استفراغ", "غثيان", "إسهال")),
    ("Skin", ("rash", "itch", "طفح", "حكة")),
)
_PLAN = ("prescribe", "start", "take", "tablet", "capsule", "syrup", "mg", "order", "test", "x-ray", "xray",
         "ultrasound", "refer", "follow up", "follow-up", "come back", "sick leave", "rest", "drink", "avoid",
         "خذ", "حبة", "شراب", "تحليل", "أشعة", "راجع", "إجازة", "تحويل")
_ASSESSMENT = ("diagnosis", "you have", "looks like", "consistent with", "التشخيص", "عندك")
_LAB = ("blood test", "cbc", "hba1c", "urine test", "lab test", "تحليل")
_IMAGING = ("x-ray", "xray", "ultrasound", "ct scan", "mri", "أشعة")
_REFERRAL = ("refer", "تحويل")
_WARNING = ("if it gets worse", "emergency", "warning", "do not", "don't", "avoid", "الطوارئ", "لا تأخذ")
_ALLERGY = ("allergic", "allergy", "allergies", "حساسية")
_SICK_LEAVE = ("sick leave", "days off", "day off", "إجازة مرضية")
_SHORTER = ("short", "brief", "concise", "أقصر", "اختصر")

_MED_RE = re.compile(
    r"\b([A-Za-z][A-Za-z\-]{2,})\s+(\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|units?|iu))\b",
    re.IGNORECASE,
)
_MED_STOPWORDS = {"take", "give", "the", "and", "of", "with", "about", "for", "start", "prescribe", "dose"}
_FOLLOW_UP_RE = re.compile(
    r"(?:follow[- ]?up|come back|see you|return)\D{0,20}?(\d+)\s*(day|week|month)s?",
    re.IGNORECASE,
)
_SICK_DAYS_RE = re.compile(
    r"(\d+)\s*days?\s*(?:of\s*)?(?:sick leave|off)|sick leave\D{0,15}(\d+)\s*days?",
    re.IGNORECASE,
)
_UNIT_DAYS = {"day": 1, "week": 7, "month": 30}


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


def _stub_record(transcript: list[dict[str, Any]]) -> dict[str, Any]:
    """Spoken vitals, measurements and pain score by keyword. First mention of a field wins."""
    record: dict[str, dict[str, Any]] = {}

    def put(group: str, name: str, value: str, seg_id: str) -> None:
        record.setdefault(group, {}).setdefault(name, {"value": value, "segment_ids": [seg_id]})

    for seg in transcript:
        text = seg["text"]
        if text.strip().endswith(("?", "؟")):
            continue
        bp = _BP_RE.search(text)
        if bp:
            put("vital_sign", "bloodPressureSystolic", bp.group(1), seg["id"])
            put("vital_sign", "bloodPressureDiastolic", bp.group(2), seg["id"])
        for group, name, pattern in _RECORD_RULES:
            match = pattern.search(text)
            if match:
                put(group, name, match.group(1), seg["id"])
    return record


def _has(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in words)


def _sentence(text: str, seg_id: str, **extra: Any) -> dict[str, Any]:
    return {"text": text, "segment_ids": [seg_id], **extra}


def stub_draft(transcript: list[dict[str, Any]], options: dict[str, Any]) -> dict[str, Any]:
    patient = [seg for seg in transcript if seg["speaker"] != "doctor"]
    doctor = [seg for seg in transcript if seg["speaker"] == "doctor"]
    known_chronic = {item.lower() for item in (options.get("patient_context") or {}).get("chronic_diseases", [])}

    chief: list[dict[str, Any]] = []
    hpi: list[dict[str, Any]] = []
    ros: list[dict[str, Any]] = []
    for index, seg in enumerate(patient):
        system = next((name for name, words in _ROS_SYSTEMS if _has(seg["text"], words)), None)
        if index == 0:
            chief.append(_sentence(seg["text"][:200], seg["id"]))
        elif system:
            ros.append(_sentence(f"{system}: {seg['text']}", seg["id"]))
        else:
            hpi.append(_sentence(seg["text"], seg["id"]))

    exam = [_sentence(seg["text"], seg["id"]) for seg in doctor if _has(seg["text"], _EXAM)]

    diagnoses: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for seg in doctor:
        for entry in icd10.find_by_text(seg["text"]):
            if entry.code in seen_codes:
                continue
            seen_codes.add(entry.code)
            diagnoses.append(
                {
                    "icd10": entry.code,
                    "label": entry.label,
                    "rank": "primary" if not diagnoses else "secondary",
                    "suspected": _has(seg["text"], _HEDGES),
                    "chronic": entry.chronic or entry.label.lower() in known_chronic,
                    "segment_ids": [seg["id"]],
                }
            )
    primary_label = diagnoses[0]["label"] if diagnoses else "No diagnosis stated"

    assessment_plan: list[dict[str, Any]] = []
    plan_segments: list[dict[str, Any]] = []
    for seg in doctor:
        if _has(seg["text"], _EXAM):
            continue
        matched = icd10.find_by_text(seg["text"])
        if matched or _has(seg["text"], _ASSESSMENT):
            label = matched[0].label if matched else primary_label
            assessment_plan.append(_sentence(f"{label}: {seg['text']}", seg["id"], part="assessment"))
        elif _has(seg["text"], _PLAN):
            plan_segments.append(seg)
            assessment_plan.append(_sentence(f"{primary_label}: {seg['text']}", seg["id"], part="plan"))

    orders: list[dict[str, Any]] = []
    mentions: list[dict[str, Any]] = []
    for seg in doctor:
        text = seg["text"]
        for name, dose in _MED_RE.findall(text):
            if name.lower() not in _MED_STOPWORDS:
                orders.append({"kind": "medication", "payload": {"name": name, "dose": dose}, "segment_ids": [seg["id"]]})
        if _has(text, _LAB):
            orders.append({"kind": "lab", "payload": {"test": text}, "segment_ids": [seg["id"]]})
        if _has(text, _IMAGING):
            orders.append({"kind": "imaging", "payload": {"test": text}, "segment_ids": [seg["id"]]})
        if _has(text, _REFERRAL):
            orders.append({"kind": "referral", "payload": {"reason": text}, "segment_ids": [seg["id"]]})
        follow = _FOLLOW_UP_RE.search(text)
        if follow:
            days = int(follow.group(1)) * _UNIT_DAYS[follow.group(2).lower()]
            orders.append({"kind": "follow_up", "payload": {"interval_days": days}, "segment_ids": [seg["id"]]})
        if _has(text, _SICK_LEAVE):
            sick = _SICK_DAYS_RE.search(text)
            payload = {"days": int(sick.group(1) or sick.group(2))} if sick else {}
            orders.append({"kind": "sick_leave", "payload": payload, "segment_ids": [seg["id"]]})
            mentions.append({"kind": "sick_leave", "text": text, "segment_ids": [seg["id"]]})
        if _has(text, _WARNING):
            mentions.append({"kind": "warning", "text": text, "segment_ids": [seg["id"]]})
    for seg in transcript:
        if _has(seg["text"], _ALLERGY):
            mentions.append({"kind": "allergy", "text": seg["text"], "segment_ids": [seg["id"]]})

    return {
        "sections": {
            "chief_complaint": {"sentences": chief},
            "hpi": {"sentences": hpi},
            "review_of_systems": {"sentences": ros},
            "physical_exam": {"sentences": exam},
            "assessment_plan": {"sentences": assessment_plan},
        },
        "diagnoses": diagnoses,
        "orders": orders,
        "mentions": mentions,
        "instructions": {
            "text": " ".join(seg["text"] for seg in plan_segments),
            "segment_ids": [seg["id"] for seg in plan_segments],
        },
        "flags": [],
        "record": _stub_record(transcript),
    }


def stub_regenerate(
    transcript: list[dict[str, Any]],
    options: dict[str, Any],
    section: str,
    instruction: str,
) -> dict[str, Any]:
    draft = stub_draft(transcript, options)
    sentences = list(draft["sections"][section]["sentences"])
    lowered = instruction.lower()
    if _has(lowered, _SHORTER) and sentences:
        sentences = sentences[: math.ceil(len(sentences) / 2)]
    elif lowered.startswith("add "):
        cited = {sid for item in sentences for sid in item["segment_ids"]}
        stems = [word[:4] for word in re.findall(r"\w+", lowered[4:]) if len(word) >= 4 and word != "history"]
        for seg in transcript:
            if seg["id"] not in cited and stems and any(stem in seg["text"].lower() for stem in stems):
                extra = {"part": "assessment"} if section == "assessment_plan" else {}
                sentences.append(_sentence(seg["text"], seg["id"], **extra))
    if section != "assessment_plan":
        return {"sentences": sentences}
    return {
        "sentences": sentences,
        **{key: draft[key] for key in ("diagnoses", "orders", "mentions", "instructions", "flags")},
    }
