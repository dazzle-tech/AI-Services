"""Picked-up list: get a raw list (model or stub), then enforce the evidence rules in code.

Whatever the model returns, only items backed by the final segments get through:
- an item must cite a final segment id (unknown ids are removed; no valid id drops the item);
- an item cited only by question lines is dropped (a question is not a finding);
- a medicine must be named in a cited segment, and numbers in its detail must appear there too;
- an exam finding's numbers must appear in a cited segment;
- an item that only restates the chart (patient_context) without being said in the visit is dropped.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.core.config import settings
from app.live import asklepios, model_client
from app.live.checks import dose_is_supported, has_negation, mentions, numbers_of, polarity_ok
from app.live.speaker import guess_speaker
from app.live.picked_up_prompts import PICKED_UP_SYSTEM_PROMPT, build_user_prompt
from app.live.picked_up_stub import stub_picked_up
from app.live.text_utils import is_question_only, normalize, sentences
from app.models.schemas import Evidence, Medication, PatientContext, PickedUp, Segment

_SPEAKER_ROLES = {"doctor", "patient"}

_ICD_PREFIX_RE = re.compile(r"^[A-Za-z]\d{2}(?:\.\w+)?\s*[-:]?\s*")
_DOSE_SUFFIX_RE = re.compile(r"\s+\d[\d.,]*\s*\w*$")
_MAX_ITEMS = 12


async def raw_extract(segments: list[Segment], context: Optional[PatientContext]) -> dict[str, Any]:
    if settings.use_llm_stub:
        return stub_picked_up(segments, context)
    return await model_client.complete_json(
        system_prompt=PICKED_UP_SYSTEM_PROMPT,
        user_prompt=build_user_prompt(segments, context),
    )


async def extract(segments: list[Segment], context: Optional[PatientContext]) -> tuple[PickedUp, dict[str, str]]:
    raw = await raw_extract(segments, context)
    return enforce_picked_up(raw, segments, context), speakers_from_model(raw, segments)


def speakers_from_model(raw: Any, segments: list[Segment]) -> dict[str, str]:
    """Speaker the model assigned to each finished line. Unknown ids and other words are dropped."""
    known = {segment.id for segment in segments if segment.final}
    labels: dict[str, str] = {}
    for seg_id, role in _speaker_entries(raw.get("speakers") if isinstance(raw, dict) else None):
        if seg_id in known and role in _SPEAKER_ROLES and seg_id not in labels:
            labels[seg_id] = role
    return labels


def _speaker_entries(value: Any):
    if isinstance(value, dict):
        pairs = value.items()
    elif isinstance(value, list):
        pairs = (
            (entry.get("id"), entry.get("speaker"))
            for entry in value
            if isinstance(entry, dict)
        )
    else:
        return
    for seg_id, role in pairs:
        yield str(seg_id or "").strip(), str(role or "").strip().lower()


def _context_forms(context: Optional[PatientContext]) -> set[str]:
    """Chart wording in comparable form: with and without an ICD code, and a medicine without its dose."""
    if context is None:
        return set()
    forms: set[str] = set()
    entries = [
        *context.chronic_diseases,
        *context.known_diagnoses,
        *context.allergies,
        *context.active_medications,
    ]
    for entry in entries:
        for variant in (entry, _ICD_PREFIX_RE.sub("", entry), _DOSE_SUFFIX_RE.sub("", entry)):
            form = normalize(variant)
            if len(form) >= 4:
                forms.add(form)
    return forms


def _joined(items: list[Evidence]) -> str:
    return ". ".join(item.text.rstrip(". ") for item in items) + "."


_PAIN_PHRASE = re.compile(
    r"\b((?:burning|dull|aching|stabbing|throbbing|cramping|radiating|tingling|shooting|sharp)\s+ache)\b",
    re.IGNORECASE,
)
_PRESSURE_PAIN = re.compile(r"\bpressure\b", re.IGNORECASE)
_BLOOD_PRESSURE = re.compile(r"\b(?:blood pressure|bp)\b", re.IGNORECASE)
_IMPRESSION = re.compile(
    r"\b(?:one possibility|can contribute|cannot confirm|i cannot confirm)\b",
    re.IGNORECASE,
)
_PLAN = re.compile(
    r"\b(?:try to|do not stop|don't stop|arrange a review|seek urgent|we can discuss)\b",
    re.IGNORECASE,
)
_CLAUSE_SPLIT = re.compile(r"\s*(?:\b(?:but|however)\b|لكن|بس)\s*", re.IGNORECASE)
_DENIAL_START = re.compile(
    r"^(?:no|not|never|without|i (?:do not|don't|have not|haven't|did not|didn't)|"
    r"لا|ما عندي|ماعندي|بدون)\b",
    re.IGNORECASE,
)
_THANKS = re.compile(r"^thank you\b", re.IGNORECASE)
_HISTORY = re.compile(
    r"\b(?:drinking less|less water|skip lunch|sleeping about|slept about)\b",
    re.IGNORECASE,
)
_BP_FILL = re.compile(r"\b(?:blood pressure|bp)\D{0,12}(\d+)\s*(?:over|/)\s*(\d+)", re.IGNORECASE)
_NUMBER_FILL: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("vital_sign", "heartRate", re.compile(r"\b(?:pulse|heart rate)\D{0,12}(\d+(?:\.\d+)?)", re.IGNORECASE)),
    ("vital_sign", "temperature", re.compile(r"\btemperature\D{0,12}(\d+(?:\.\d+)?)", re.IGNORECASE)),
    ("vital_sign", "oxygenSaturation", re.compile(r"\b(?:oxygen saturation|spo2)\D{0,12}(\d+(?:\.\d+)?)", re.IGNORECASE)),
    ("vital_sign", "respiratoryRate", re.compile(r"\brespiratory rate\D{0,12}(\d+(?:\.\d+)?)", re.IGNORECASE)),
    ("body_measurements", "weight", re.compile(r"\bweight\D{0,12}(\d+(?:\.\d+)?)\s*(?:kg|kilo)", re.IGNORECASE)),
    ("body_measurements", "height", re.compile(r"\bheight\D{0,12}(\d+(?:\.\d+)?)\s*(?:cm|centimet)", re.IGNORECASE)),
    ("body_measurements", "headCircumference", re.compile(r"\bhead circumference\D{0,16}(\d+(?:\.\d+)?)", re.IGNORECASE)),
    ("pain_assessment", "painLevel", re.compile(r"\bpain(?: score| level)?\D{0,12}(\d+)\s*(?:out of|/)\s*10", re.IGNORECASE)),
)


def _store_spoken_number(
    values: dict[str, dict[str, Any]],
    evidence: dict[str, list[str]],
    group: str,
    name: str,
    raw: str,
    seg_id: str,
) -> None:
    """Same ranges as the draft: a spoken number fills a record field the model left empty."""
    spec = asklepios.FIELDS[group][name]
    try:
        number = float(raw)
    except ValueError:
        return
    bucket = values.setdefault(group, {})
    if bucket.get(name) not in (None, ""):
        return
    if name == "height" and 0.4 <= number <= 2.6:
        number = round(number * 100, 1)
    if not spec.low <= number <= spec.high:
        return
    if spec.kind in ("int", "pain_level") and abs(number - round(number)) > 0.001:
        return
    if spec.kind == "pain_level":
        value: Any = f"LEVEL_{int(round(number))}"
    elif spec.kind == "int":
        value = int(round(number))
    else:
        value = int(number) if abs(number - round(number)) < 0.001 else round(number, 1)
    bucket[name] = value
    evidence[f"{group}.{name}"] = [seg_id]
    if name == "painLevel" and not bucket.get("painAssessmentType"):
        bucket["painAssessmentType"] = "NUMERIC"
        evidence["pain_assessment.painAssessmentType"] = [seg_id]


def _fill_spoken_numbers(
    values: dict[str, dict[str, Any]],
    evidence: dict[str, list[str]],
    texts: dict[str, str],
    questions: set[str],
) -> None:
    for seg_id, text in texts.items():
        if seg_id in questions:
            continue
        bp = _BP_FILL.search(text)
        if bp:
            systolic, diastolic = float(bp.group(1)), float(bp.group(2))
            if systolic > diastolic:
                _store_spoken_number(values, evidence, "vital_sign", "bloodPressureSystolic", bp.group(1), seg_id)
                _store_spoken_number(values, evidence, "vital_sign", "bloodPressureDiastolic", bp.group(2), seg_id)
        for group, name, pattern in _NUMBER_FILL:
            match = pattern.search(text)
            if match:
                _store_spoken_number(values, evidence, group, name, match.group(1), seg_id)


def _statements(text: str) -> list[str]:
    kept: list[str] = []
    for sentence in sentences(text):
        if sentence.endswith(("?", "؟")) or _THANKS.match(sentence):
            continue
        kept.append(sentence.strip())
    return kept


def _fill_spoken_pain_description(
    values: dict[str, dict[str, Any]],
    evidence: dict[str, list[str]],
    texts: dict[str, str],
    questions: set[str],
) -> None:
    group = values.setdefault("pain_assessment", {})
    for seg_id, text in texts.items():
        if seg_id in questions:
            continue
        if not group.get("painDescription"):
            match = _PAIN_PHRASE.search(text)
            if match:
                group["painDescription"] = match.group(1).lower()
                evidence["pain_assessment.painDescription"] = [seg_id]
        if _PRESSURE_PAIN.search(text) and not _BLOOD_PRESSURE.search(text):
            if not group.get("painDescription"):
                group["painDescription"] = "pressure"
                evidence["pain_assessment.painDescription"] = [seg_id]
            if not group.get("painPattern"):
                group["painPattern"] = "Pressure-like"
                evidence["pain_assessment.painPattern"] = [seg_id]


def _fill_spoken_impression_and_plan(
    values: dict[str, dict[str, Any]],
    evidence: dict[str, list[str]],
    texts: dict[str, str],
    questions: set[str],
) -> None:
    """Copy the clinician's spoken impression and home-care advice when the model leaves those groups empty."""
    assessment = values.setdefault("assessment", {})
    plan = values.setdefault("plan_of_care", {})
    impressions: list[str] = []
    plans: list[str] = []
    impression_ids: list[str] = []
    plan_ids: list[str] = []
    for seg_id, text in texts.items():
        if seg_id in questions:
            continue
        statements = _statements(text)
        blob = " ".join(statements)
        if not blob:
            continue
        if not assessment.get("assessment") and _IMPRESSION.search(blob):
            impressions.append(blob)
            impression_ids.append(seg_id)
        if not plan.get("treatmentPlan") and _PLAN.search(blob):
            plans.append(blob)
            plan_ids.append(seg_id)
    if impressions and not assessment.get("assessment"):
        assessment["assessment"] = " ".join(impressions)
        evidence["assessment.assessment"] = impression_ids
    if plans and not plan.get("treatmentPlan"):
        plan["treatmentPlan"] = " ".join(plans)
        evidence["plan_of_care.treatmentPlan"] = plan_ids


def _fill_spoken_denials(
    symptoms: list[Evidence],
    texts: dict[str, str],
    questions: set[str],
) -> None:
    """Keep a denial the patient actually said, such as "no nausea or vomiting"."""
    existing = {normalize(item.text) for item in symptoms}
    for seg_id, text in texts.items():
        if seg_id in questions or guess_speaker(text) != "patient":
            continue
        for sentence in sentences(text):
            if sentence.endswith(("?", "؟")):
                continue
            for clause in _CLAUSE_SPLIT.split(sentence):
                clause = clause.strip(" .,;:")
                if len(clause) < 4 or not _DENIAL_START.match(clause) or not has_negation(clause):
                    continue
                key = normalize(clause)
                if not key or any(key == other or key in other or other in key for other in existing):
                    continue
                symptoms.append(Evidence(text=clause, segment_ids=[seg_id]))
                existing.add(key)
                if len(symptoms) >= _MAX_ITEMS:
                    return
            if len(symptoms) >= _MAX_ITEMS:
                return
            for clause in _CLAUSE_SPLIT.split(sentence):
                clause = clause.strip(" .,;:")
                if len(clause) < 4 or not _HISTORY.search(clause):
                    continue
                key = normalize(clause)
                if not key or any(key == other or key in other or other in key for other in existing):
                    continue
                symptoms.append(Evidence(text=clause, segment_ids=[seg_id]))
                existing.add(key)
                if len(symptoms) >= _MAX_ITEMS:
                    return


def _build_record(
    raw: dict[str, Any],
    texts: dict[str, str],
    questions: set[str],
    complaint: Optional[Evidence],
    symptoms: list[Evidence],
    exam: list[Evidence],
    context: Optional[PatientContext],
) -> asklepios.Record:
    """Measured fields come from the model (checked); text fields come from the lists already checked above."""
    values, evidence = asklepios.clean_record(raw.get("record"), texts, questions, asklepios.LIVE_MODEL_GROUPS)
    _fill_spoken_numbers(values, evidence, texts, questions)
    _fill_spoken_pain_description(values, evidence, texts, questions)
    _fill_spoken_impression_and_plan(values, evidence, texts, questions)

    def put(group: str, name: str, text: str, ids: list[str]) -> None:
        values.setdefault(group, {})[name] = text
        evidence[f"{group}.{name}"] = ids

    def union(items: list[Evidence]) -> list[str]:
        return list(dict.fromkeys(seg_id for item in items for seg_id in item.segment_ids))

    if complaint is not None:
        put("clinical_visit", "chiefComplaint", complaint.text, complaint.segment_ids)
        put("nursing_assessment", "reasonOfVisit", complaint.text, complaint.segment_ids)
    if symptoms:
        put("clinical_visit", "historyOfPresentIllness", _joined(symptoms), union(symptoms))
    if exam:
        put("clinical_visit", "physicalExaminationSummery", _joined(exam), union(exam))
    conditions = ", ".join(context.chronic_diseases) if context and context.chronic_diseases else None
    return asklepios.assemble(
        values,
        evidence,
        patient_conditions=conditions or None,
        groups=[group for group in asklepios.GROUP_ORDER if group != "patient_diagnosis"],
    )


def enforce_picked_up(
    raw: Any,
    segments: list[Segment],
    context: Optional[PatientContext],
) -> PickedUp:
    raw = raw if isinstance(raw, dict) else {}
    by_id = {segment.id: segment for segment in segments if segment.final}
    questions = {seg_id for seg_id, segment in by_id.items() if is_question_only(segment.text)}
    forms = _context_forms(context)

    def cite(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        ids: list[str] = []
        for item in value:
            seg_id = str(item).strip()
            if seg_id in by_id and seg_id not in ids:
                ids.append(seg_id)
        if ids and all(seg_id in questions for seg_id in ids):
            return []
        return ids

    def heard(ids: list[str]) -> str:
        return normalize(" ".join(by_id[seg_id].text for seg_id in ids))

    def restates_chart(text: str, spoken: str) -> bool:
        norm = normalize(text)
        return any((norm == form or (len(form) >= 4 and form in norm)) and form not in spoken for form in forms)

    def items(value: Any, *, check_numbers: bool = False) -> list[Evidence]:
        result: list[Evidence] = []
        seen: set[str] = set()
        for entry in value if isinstance(value, list) else []:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or "").strip()
            ids = cite(entry.get("segment_ids"))
            if not text or not ids:
                continue
            spoken = heard(ids)
            if restates_chart(text, spoken):
                continue
            if check_numbers and not numbers_of(text) <= numbers_of(spoken):
                continue
            key = normalize(text)
            if key in seen:
                continue
            seen.add(key)
            result.append(Evidence(text=text, segment_ids=ids))
            if len(result) >= _MAX_ITEMS:
                break
        return result

    complaint = (items([raw.get("complaint")]) or [None])[0] if isinstance(raw.get("complaint"), dict) else None

    medications: list[Medication] = []
    named: set[str] = set()
    for entry in raw.get("medications") if isinstance(raw.get("medications"), list) else []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        ids = cite(entry.get("segment_ids"))
        if not name or not ids or normalize(name) in named:
            continue
        spoken_raw = " ".join(by_id[seg_id].text for seg_id in ids)
        if not mentions(spoken_raw, name):
            continue  # not said in this visit (for example copied from the chart)
        detail = str(entry.get("detail") or "").strip() or None
        if detail and not dose_is_supported(detail, spoken_raw):
            detail = None  # an invented or changed dose is worse than none
        named.add(normalize(name))
        medications.append(Medication(name=name, detail=detail, segment_ids=ids))
        if len(medications) >= _MAX_ITEMS:
            break

    def agreed(item: Optional[Evidence]) -> Optional[Evidence]:
        if item is None:
            return None
        cited = [by_id[seg_id].text for seg_id in item.segment_ids]
        return item if polarity_ok(item.text, cited) else None

    complaint = agreed(complaint)
    symptoms = [item for item in items(raw.get("symptoms")) if agreed(item) is not None]
    exam = [item for item in items(raw.get("exam"), check_numbers=True) if agreed(item) is not None]
    texts = {seg_id: segment.text for seg_id, segment in by_id.items()}
    _fill_spoken_denials(symptoms, texts, questions)
    record = _build_record(raw, texts, questions, complaint, symptoms, exam, context)
    return PickedUp(
        complaint=complaint,
        symptoms=symptoms,
        medications=medications,
        exam=exam,
        record=record.record,
        record_evidence=record.evidence,
        record_status=record.status,
        missing_required=record.missing_required,
    )
