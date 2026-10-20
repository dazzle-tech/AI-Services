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
from app.live.picked_up_prompts import PICKED_UP_SYSTEM_PROMPT, build_user_prompt
from app.live.picked_up_stub import stub_picked_up
from app.live.text_utils import is_question_only, normalize
from app.models.schemas import Evidence, Medication, PatientContext, PickedUp, Segment

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
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


async def extract(
    segments: list[Segment],
    context: Optional[PatientContext],
    *,
    patient_id: Optional[int] = None,
    encounter_id: Optional[int] = None,
) -> PickedUp:
    raw = await raw_extract(segments, context)
    return enforce_picked_up(raw, segments, context, patient_id=patient_id, encounter_id=encounter_id)


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


def _numbers(text: str) -> set[str]:
    return {number.replace(",", ".") for number in _NUMBER_RE.findall(text)}


def _joined(items: list[Evidence]) -> str:
    return ". ".join(item.text.rstrip(". ") for item in items) + "."


def _build_record(
    raw: dict[str, Any],
    texts: dict[str, str],
    questions: set[str],
    complaint: Optional[Evidence],
    symptoms: list[Evidence],
    exam: list[Evidence],
    context: Optional[PatientContext],
    patient_id: Optional[int],
    encounter_id: Optional[int],
) -> asklepios.Record:
    """Measured fields come from the model (checked); text fields come from the lists already checked above."""
    values, evidence = asklepios.clean_record(raw.get("record"), texts, questions, asklepios.LIVE_MODEL_GROUPS)

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
        patient_id=patient_id,
        encounter_id=encounter_id,
        patient_conditions=conditions or None,
        groups=[group for group in asklepios.GROUP_ORDER if group != "patient_diagnosis"],
    )


def enforce_picked_up(
    raw: Any,
    segments: list[Segment],
    context: Optional[PatientContext],
    *,
    patient_id: Optional[int] = None,
    encounter_id: Optional[int] = None,
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
            if check_numbers and not _numbers(text) <= _numbers(spoken):
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
        spoken = heard(ids)
        if normalize(name) not in spoken:
            continue  # not said in this visit (for example copied from the chart)
        detail = str(entry.get("detail") or "").strip() or None
        if detail and not _numbers(detail) <= _numbers(spoken):
            detail = None  # an invented dose is worse than none
        named.add(normalize(name))
        medications.append(Medication(name=name, detail=detail, segment_ids=ids))
        if len(medications) >= _MAX_ITEMS:
            break

    symptoms = items(raw.get("symptoms"))
    exam = items(raw.get("exam"), check_numbers=True)
    texts = {seg_id: segment.text for seg_id, segment in by_id.items()}
    record = _build_record(raw, texts, questions, complaint, symptoms, exam, context, patient_id, encounter_id)
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
