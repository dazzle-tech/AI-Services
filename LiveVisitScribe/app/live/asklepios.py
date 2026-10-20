"""Asklepios record payloads: which fields exist, what counts as evidence, and how the payloads are built.

Same file in ConvoVoiceAgent and LiveVisitScribe (the services stay independent, so it is copied, not shared).

A model (or the stub) proposes fields as {"value": ..., "segment_ids": [...]}. Code decides what survives:
- a field must cite a segment that exists, and a segment that is only a question never counts;
- a number must be said in a cited segment (nothing is calculated or converted, except height in metres);
- a number must be plausible for its field (a heart rate of 7 is a misheard number, not a finding);
- an enum value must be one the backend knows; anything else is dropped, never sent;
- required fields that were not said stay missing and are listed, so the clinician fills them in.

Nothing here invents a value. The only constants are the ones the form always sends:
isActive=true, isTriage=false, byPatient=true, priorityLevel=NORMAL, painAssessmentType=NUMERIC when a pain score was said.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_EPS = 1e-9

# Enum values. Confirmed = appears in the backend's sample payloads; the rest are assumed siblings.
# Keep this table in step with the backend: a value that is not listed here is dropped, never sent.
ENUMS: dict[str, frozenset[str]] = {
    "measurementSite": frozenset({"LEFT_ARM", "RIGHT_ARM", "LEFT_LEG", "RIGHT_LEG"}),  # confirmed: LEFT_ARM
    "fluidStatus": frozenset({"EUVOLEMIC", "HYPOVOLEMIC", "HYPERVOLEMIC"}),  # confirmed: EUVOLEMIC
    "edema": frozenset({"NONE", "MILD", "MODERATE", "SEVERE"}),  # confirmed: NONE
    "urineOutput": frozenset({"NORMAL", "DECREASED", "INCREASED"}),  # confirmed: NORMAL
    "painDegree": frozenset({"MILD", "MODERATE", "SEVERE"}),  # confirmed: MODERATE
    "painPattern": frozenset({"INTERMITTENT", "CONSTANT"}),  # confirmed: INTERMITTENT
    "painAssessmentType": frozenset({"NUMERIC", "FACES"}),  # confirmed: NUMERIC
    "modeOfArrival": frozenset({"WALK_IN", "WHEELCHAIR", "STRETCHER", "AMBULANCE"}),  # confirmed: WALK_IN
}


# An enum value is accepted only if a cited segment talks about that topic at all. This stops "edema NONE"
# resting on a line about pulse; it does not judge whether the value itself is right (the physician does).
_ENUM_CUES: dict[str, re.Pattern[str]] = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in {
        "measurementSite": r"\b(?:arm|leg|left|right)\b|ذراع|يد|رجل|يمين|يسار",
        "fluidStatus": r"fluid|volume|hydrat|euvol|hypovol|hypervol|سوائل|جفاف",
        "edema": r"edema|oedema|swell|swollen|puff|وذمة|تورم|انتفاخ",
        "urineOutput": r"urin|output|pee|void|بول|تبول",
        "painDegree": r"\b(?:mild|moderate|severe|slight|bad|terrible|unbearable)\b|خفيف|متوسط|شديد|قوي",
        "painPattern": r"intermittent|constant|continuous|comes and goes|on and off|all the time|متقطع|مستمر|دائم",
        "painAssessmentType": r"out of|/\s*10|scale|score|face|مقياس|من 10",
        "modeOfArrival": r"walk|wheelchair|stretcher|ambulance|carried|brought|came|إسعاف|كرسي|نقالة|مشي",
    }.items()
}


@dataclass(frozen=True)
class Spec:
    kind: str  # int | number | numstr | pain_level | enum | text
    low: float = 0.0
    high: float = 0.0


FIELDS: dict[str, dict[str, Spec]] = {
    "vital_sign": {
        "bloodPressureSystolic": Spec("int", 50, 300),
        "bloodPressureDiastolic": Spec("int", 20, 200),
        "measurementSite": Spec("enum"),
        "heartRate": Spec("int", 20, 300),
        "temperature": Spec("number", 25, 45),  # Celsius; Fahrenheit is out of range and dropped
        "oxygenSaturation": Spec("int", 50, 100),
        "respiratoryRate": Spec("int", 4, 80),
        "fastingBloodGlucose": Spec("numstr", 10, 1000),
        "fluidStatus": Spec("enum"),
        "edema": Spec("enum"),
        "urineOutput": Spec("enum"),
        "notes": Spec("text"),
    },
    "body_measurements": {
        "weight": Spec("number", 0.3, 500),  # kg
        "height": Spec("number", 20, 250),  # cm; metres (0.4-2.6) are multiplied by 100
        "headCircumference": Spec("number", 15, 80),  # cm
    },
    "pain_assessment": {
        "painDegree": Spec("enum"),
        "painDescription": Spec("text"),
        "painPattern": Spec("enum"),
        "painLevel": Spec("pain_level", 0, 10),
        "painAssessmentType": Spec("enum"),
    },
    "nursing_assessment": {
        "reasonOfVisit": Spec("text"),
        "modeOfArrival": Spec("enum"),
        "functionalStatus": Spec("text"),
        "cognitiveCheck": Spec("text"),
    },
    "clinical_visit": {
        "chiefComplaint": Spec("text"),
        "historyOfPresentIllness": Spec("text"),
        "physicalExaminationSummery": Spec("text"),
    },
    "assessment": {"assessment": Spec("text")},
    "plan_of_care": {"goals": Spec("text"), "treatmentPlan": Spec("text")},
}

# Payload layout: every key the backend takes, in order. Missing values are null.
LAYOUT: dict[str, tuple[str, ...]] = {
    "vital_sign": (
        "patientId", "encounterId", "bloodPressureSystolic", "bloodPressureDiastolic", "measurementSite",
        "heartRate", "temperature", "oxygenSaturation", "respiratoryRate", "fastingBloodGlucose", "fluidStatus",
        "edema", "urineOutput", "isTriage", "isActive", "notes",
    ),
    "body_measurements": ("patientId", "encounterId", "weight", "height", "headCircumference", "isActive"),
    "pain_assessment": (
        "patientId", "encounterId", "painDegree", "painDescription", "painPattern", "painLevel",
        "painAssessmentType", "isActive",
    ),
    "nursing_assessment": (
        "patientId", "encounterId", "reasonOfVisit", "modeOfArrival", "byPatient", "sourceOfInformation",
        "functionalStatus", "patientConditions", "cognitiveCheck", "bloodGroup", "isActive", "priorityLevel",
    ),
    "clinical_visit": ("chiefComplaint", "historyOfPresentIllness", "physicalExaminationSummery"),
    "assessment": ("patientId", "encounterId", "assessment"),
    "plan_of_care": ("patientId", "encounterId", "goals", "treatmentPlan"),
}
WITH_IDS = {"vital_sign", "body_measurements", "pain_assessment", "nursing_assessment", "assessment", "plan_of_care"}
DEFAULTS: dict[str, dict[str, Any]] = {
    "vital_sign": {"isTriage": False, "isActive": True},
    "body_measurements": {"isActive": True},
    "pain_assessment": {"isActive": True},
    "nursing_assessment": {"byPatient": True, "isActive": True, "priorityLevel": "NORMAL"},
}
REQUIRED: dict[str, tuple[str, ...]] = {
    "vital_sign": (
        "bloodPressureSystolic", "bloodPressureDiastolic", "heartRate", "temperature", "oxygenSaturation",
        "respiratoryRate",
    ),
    "body_measurements": ("weight", "height"),
    "pain_assessment": ("painDegree",),
    "nursing_assessment": ("reasonOfVisit",),
}
GROUP_ORDER = (
    "vital_sign", "body_measurements", "pain_assessment", "nursing_assessment", "clinical_visit",
    "patient_diagnosis", "assessment", "plan_of_care",
)
# What the model is asked for in ConvoVoiceAgent /draft (the rest is built from the note sections).
DRAFT_MODEL_GROUPS = ("vital_sign", "body_measurements", "pain_assessment", "nursing_assessment", "plan_of_care")
# What the model is asked for in LiveVisitScribe (the rest is built from the picked-up lists).
LIVE_MODEL_GROUPS = (
    "vital_sign", "body_measurements", "pain_assessment", "nursing_assessment", "assessment", "plan_of_care",
)


@dataclass
class Record:
    record: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, list[str]] = field(default_factory=dict)
    status: dict[str, str] = field(default_factory=dict)
    missing_required: dict[str, list[str]] = field(default_factory=dict)


# --- Cleaning model output -------------------------------------------------


def _numbers(text: str) -> set[float]:
    return {float(match.replace(",", ".")) for match in _NUMBER_RE.findall(text)}


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = _NUMBER_RE.search(value)
        return float(match.group(0).replace(",", ".")) if match else None
    return None


def _spoken(number: float, spoken: set[float]) -> bool:
    return any(abs(number - item) < _EPS for item in spoken)


def _plain(number: float) -> int | float:
    return int(round(number)) if abs(number - round(number)) < _EPS else round(number, 2)


def _coerce(spec: Spec, name: str, value: Any, spoken: set[float], heard: str) -> Any:
    if spec.kind == "text":
        text = str(value or "").strip()
        if not text or len(text) > 2000:
            return None
        return text if _numbers(text) <= spoken else None  # a number in free text must have been said
    if spec.kind == "enum":
        key = re.sub(r"[\s\-]+", "_", str(value or "").strip().upper())
        if key not in ENUMS.get(name, frozenset()):
            return None
        cue = _ENUM_CUES.get(name)
        return key if cue is None or cue.search(heard) else None

    number = _to_float(value)
    if number is None or not _spoken(number, spoken):
        return None
    if name == "height" and 0.4 <= number <= 2.6:
        number = round(number * 100, 1)  # metres to centimetres: exact, not a guess
    if not spec.low <= number <= spec.high:
        return None
    if spec.kind == "pain_level":
        return f"LEVEL_{int(number)}" if abs(number - round(number)) < _EPS else None
    if spec.kind == "int":
        return int(round(number)) if abs(number - round(number)) < _EPS else None
    if spec.kind == "numstr":
        return str(_plain(number))
    return _plain(number)


def _cite(value: Any, texts: Mapping[str, str], questions: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        seg_id = str(item).strip()
        if seg_id in texts and seg_id not in ids:
            ids.append(seg_id)
    if ids and all(seg_id in questions for seg_id in ids):
        return []
    return ids


def clean_record(
    raw: Any,
    texts: Mapping[str, str],
    questions: set[str],
    groups: Iterable[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Keep only fields that pass the evidence rules. Returns (values by group, segment ids by "group.field")."""
    values: dict[str, dict[str, Any]] = {}
    evidence: dict[str, list[str]] = {}
    raw = raw if isinstance(raw, dict) else {}
    for group in groups:
        raw_group = raw.get(group)
        if not isinstance(raw_group, dict):
            continue
        for name, spec in FIELDS[group].items():
            entry = raw_group.get(name)
            if not isinstance(entry, dict):
                continue
            ids = _cite(entry.get("segment_ids"), texts, questions)
            if not ids:
                continue
            heard = " ".join(texts[seg_id] for seg_id in ids)
            value = _coerce(spec, name, entry.get("value"), _numbers(heard), heard)
            if value is None:
                continue
            values.setdefault(group, {})[name] = value
            evidence[f"{group}.{name}"] = ids

    vital = values.get("vital_sign", {})
    systolic, diastolic = vital.get("bloodPressureSystolic"), vital.get("bloodPressureDiastolic")
    if systolic is not None and diastolic is not None and systolic <= diastolic:
        for name in ("bloodPressureSystolic", "bloodPressureDiastolic"):  # a swapped or misheard pair: ask again
            del vital[name]
            evidence.pop(f"vital_sign.{name}", None)

    pain = values.get("pain_assessment", {})
    if "painLevel" in pain and "painAssessmentType" not in pain:
        pain["painAssessmentType"] = "NUMERIC"
        evidence["pain_assessment.painAssessmentType"] = evidence["pain_assessment.painLevel"]
    return values, evidence


# --- Building payloads -----------------------------------------------------


def assemble(
    values: Mapping[str, Mapping[str, Any]],
    evidence: Mapping[str, list[str]],
    *,
    patient_id: int | None = None,
    encounter_id: int | None = None,
    patient_conditions: str | None = None,
    groups: Iterable[str] = GROUP_ORDER,
    diagnoses: list[Mapping[str, Any]] | None = None,
    sparse: bool = False,
) -> Record:
    """Payloads in the backend's shape.

    A group with nothing found is null (status "empty"): do not post it. A group with some fields is posted
    once `missing_required` for it is empty. `sparse=True` (section regenerate) returns only the keys that were
    actually computed, so the caller never overwrites a field the section does not cover.
    """
    result = Record(evidence={key: list(ids) for key, ids in evidence.items()})
    ids = {"patientId": patient_id, "encounterId": encounter_id}
    wanted = set(groups)

    for group in GROUP_ORDER:
        if group not in wanted:
            continue
        if group == "patient_diagnosis":
            if diagnoses is None:
                continue
            items = []
            for index, dx in enumerate(diagnoses):
                items.append(
                    {
                        **ids,
                        "diagnosisId": None,  # resolve from the ICD-10 code in `diagnoses`; this service has no catalog
                        "type": "PRIMARY" if dx.get("rank") == "primary" else "SECONDARY",
                        "suspected": bool(dx.get("suspected")),
                        "major": dx.get("rank") == "primary",
                    }
                )
                result.evidence[f"patient_diagnosis.{index}"] = list(dx.get("segment_ids") or [])
            result.record[group] = items
            result.status[group] = "complete" if items else "empty"
            continue

        found = values.get(group, {})
        present = {name: value for name, value in found.items() if sparse or value is not None}
        real = {name: value for name, value in present.items() if value is not None}
        if sparse:
            if not present:
                continue
            result.record[group] = {**(ids if group in WITH_IDS else {}), **present}
            continue
        if not real:
            result.record[group] = None
            result.status[group] = "empty"
            continue
        payload: dict[str, Any] = {key: None for key in LAYOUT[group]}
        payload.update(DEFAULTS.get(group, {}))
        if group in WITH_IDS:
            payload.update(ids)
        if group == "nursing_assessment":
            payload["patientConditions"] = patient_conditions
        payload.update(real)
        result.record[group] = payload
        missing = [name for name in REQUIRED.get(group, ()) if name not in real]
        result.status[group] = "partial" if missing else "complete"
        if missing:
            result.missing_required[group] = missing
    return result
