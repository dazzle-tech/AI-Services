"""Ambient draft: transcript ids, note generation, and the evidence rules every draft passes through.

The note model (or the stub) proposes items with segment_ids. Nothing reaches the caller unless it
cites at least one segment that exists in this transcript.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.ai import ambient_stub
from app.ai.ambient_prompts import build_draft_user_prompt, build_regenerate_user_prompt, build_system_prompt
from app.ai.note_model import complete_json
from app.clinical import asklepios, icd10
from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import (
    SECTION_NAMES,
    Diagnosis,
    Flag,
    Instructions,
    Mention,
    NoteOptions,
    Order,
    PatientContext,
    PlanSentence,
    Sentence,
    TranscriptionErrorHint,
    TranscriptItem,
)

logger = get_logger(__name__)

SOAP_NOTE_FIELDS: tuple[str, ...] = (
    "ChiefComplaint",
    "HPI",
    "MedicalHistory",
    "SurgicalHistory",
    "FamilyAndSocialHistory",
    "OtherSubjective",
    "Vitals",
    "PhysicalExamination",
    "Assessments",
    "DiagnosticImagesAndTests",
    "Procedures",
    "TreatmentPlans",
)
SECTION_SOAP_FIELDS: dict[str, tuple[str, ...]] = {
    "chief_complaint": ("ChiefComplaint",),
    "hpi": ("HPI", "MedicalHistory"),
    "review_of_systems": ("PhysicalExamination",),
    "physical_exam": ("Vitals", "PhysicalExamination"),
    "assessment_plan": ("Assessments", "TreatmentPlans"),
}
_HISTORY_PREFIXES = ("history:", "medical history:", "التاريخ المرضي:")
_VITALS_PREFIXES = ("vitals:", "vital signs:", "العلامات الحيوية:")
_MEASUREMENT_PREFIXES = ("measurements:", "القياسات:")
_SENTENCE_PREFIX = {
    "chief_complaint": "cc",
    "hpi": "hpi",
    "review_of_systems": "ros",
    "physical_exam": "pe",
    "assessment_plan": "ap",
}
_ROS_LABEL = {"english": "Review of systems:", "arabic": "مراجعة الأجهزة:"}
_ORDER_KINDS = {"medication", "lab", "imaging", "referral", "follow_up", "sick_leave"}
_MENTION_KINDS = {"allergy", "warning", "sick_leave"}
_FLAG_KINDS = {"drug_name", "dose"}

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_DOSE_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s?(?:mg|mcg|µg|g|ml|units?|iu|ملغ|مجم|ملغم|مل|وحدة)(?!\w)",
    re.IGNORECASE,
)
_LANG_ALIASES = {"en": "en", "english": "en", "ar": "ar", "arabic": "ar", "mixed": "mixed"}
_UTTERANCE_RE = re.compile(r"[^.!?؟]+[.!?؟]*")
_FREQUENCY_RE = re.compile(
    r"\b(?:as needed|prn|daily|once|twice|times|every|morning|night|nightly|bedtime|hourly|weekly)\b"
    r"|مرة|مرتين|يوميا|يومياً|كل|عند الحاجة|صباحا|مساء",
    re.IGNORECASE,
)
_PLAN_LABEL_RE = re.compile(r"^([^\W\d][^:\n]{1,79}):\s+(\S.*)$", re.DOTALL)


@dataclass
class DraftParts:
    sections: dict[str, list[Sentence]]
    diagnoses: list[Diagnosis] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)
    instructions: Instructions | None = None
    flags: list[Flag] = field(default_factory=list)
    transcription_errors: list[TranscriptionErrorHint] = field(default_factory=list)
    measured: dict[str, dict[str, Any]] = field(default_factory=dict)
    measured_evidence: dict[str, list[str]] = field(default_factory=dict)


# --- Transcript ------------------------------------------------------------


def build_transcript(analyzed: dict[str, Any]) -> list[TranscriptItem]:
    """Assign ids s1..sN to ConvoScribe segments. Speaker comes from role_map."""
    raw = analyzed.get("raw_transcript") if isinstance(analyzed.get("raw_transcript"), dict) else {}
    role_map = analyzed.get("role_map") if isinstance(analyzed.get("role_map"), dict) else {}
    items: list[TranscriptItem] = []
    for segment in raw.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        role = role_map.get(segment.get("speaker_label"))
        items.append(
            TranscriptItem(
                id=f"s{len(items) + 1}",
                speaker=role if role in ("doctor", "patient", "other") else "other",
                lang=_segment_lang(segment, text),
                start_ms=int(round(float(segment.get("start_time") or 0) * 1000)),
                end_ms=int(round(float(segment.get("end_time") or 0) * 1000)),
                text=text,
                confidence=_segment_confidence(segment),
            )
        )
    return items


def _segment_lang(segment: dict[str, Any], text: str) -> str:
    declared = str(segment.get("lang") or segment.get("language") or "").strip().lower()
    if declared in _LANG_ALIASES:
        return _LANG_ALIASES[declared]
    has_ar = bool(_ARABIC_RE.search(text))
    has_en = bool(_LATIN_RE.search(text))
    if has_ar and has_en:
        return "mixed"
    if has_ar:
        return "ar"
    if has_en:
        return "en"
    return "unknown"


def _segment_confidence(segment: dict[str, Any]) -> float | None:
    """Per-segment ASR confidence when the transcription backend reports one."""
    value = segment.get("confidence")
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    logprob = segment.get("avg_logprob")
    if isinstance(logprob, (int, float)):
        return max(0.0, min(1.0, math.exp(float(logprob))))
    return None


def low_confidence_ids(transcript: list[TranscriptItem]) -> set[str]:
    threshold = settings.ambient_low_confidence_threshold
    return {item.id for item in transcript if item.confidence is not None and item.confidence < threshold}


def model_transcript(transcript: list[TranscriptItem]) -> list[dict[str, Any]]:
    low = low_confidence_ids(transcript)
    return [
        {"id": item.id, "speaker": item.speaker, "lang": item.lang, "text": item.text, "low_confidence": item.id in low}
        for item in transcript
    ]


# --- Generation ------------------------------------------------------------


def patient_context_used(context: PatientContext | None) -> bool:
    if context is None:
        return False
    return bool(context.chronic_diseases or context.active_medications or context.allergies or context.last_visit)


def _model_options(options: NoteOptions) -> dict[str, Any]:
    return {
        "note_language": options.note_language,
        "instruction_language": options.resolved_instruction_language,
        "specialty": options.specialty,
        "note_length": options.note_length,
        "note_form": options.note_form,
    }


def _context_payload(options: NoteOptions) -> dict[str, Any] | None:
    if not patient_context_used(options.patient_context):
        return None
    return options.patient_context.model_dump(exclude_none=True)


async def generate_draft(transcript: list[TranscriptItem], options: NoteOptions) -> DraftParts:
    segments = model_transcript(transcript)
    if settings.use_llm_stub:
        raw = ambient_stub.stub_draft(segments, {**_model_options(options), "patient_context": _context_payload(options)})
    else:
        raw = await complete_json(
            system_prompt=build_system_prompt(
                specialty=options.specialty, note_length=options.note_length, note_form=options.note_form
            ),
            user_prompt=build_draft_user_prompt(
                transcript=segments, options=_model_options(options), patient_context=_context_payload(options)
            ),
        )
    return enforce_evidence(raw, transcript, options)


_PLAN_ONLY_KEYS = ("diagnoses", "orders", "mentions", "instructions")
_SECTION_KEYS = ("flags", "possible_transcription_errors")


async def regenerate_section(
    transcript: list[TranscriptItem],
    options: NoteOptions,
    section: str,
    instruction: str,
) -> DraftParts:
    """Same evidence rules as the full draft, scoped to one section."""
    segments = model_transcript(transcript)
    if settings.use_llm_stub:
        raw = ambient_stub.stub_regenerate(
            segments, {**_model_options(options), "patient_context": _context_payload(options)}, section, instruction
        )
    else:
        raw = await complete_json(
            system_prompt=build_system_prompt(
                specialty=options.specialty, note_length=options.note_length, note_form=options.note_form
            ),
            user_prompt=build_regenerate_user_prompt(
                section=section,
                instruction=instruction,
                transcript=segments,
                options=_model_options(options),
                patient_context=_context_payload(options),
            ),
        )
    raw = raw if isinstance(raw, dict) else {}
    keys = _SECTION_KEYS + (_PLAN_ONLY_KEYS if section == "assessment_plan" else ())
    scoped = {key: raw.get(key) for key in keys}
    scoped["sections"] = {section: {"sentences": raw.get("sentences")}}
    parts = enforce_evidence(scoped, transcript, options)
    parts.sections = {section: parts.sections[section]}

    cited = {seg_id for sentence in parts.sections[section] for seg_id in sentence.segment_ids}
    for item in (*parts.diagnoses, *parts.orders, *parts.mentions):
        cited.update(item.segment_ids)
    parts.flags = [flag for flag in parts.flags if cited.intersection(flag.segment_ids)]
    parts.transcription_errors = [
        hint for hint in parts.transcription_errors if cited.intersection(hint.segment_ids)
    ]
    if section != "assessment_plan":
        parts.instructions = None
    return parts


# --- Evidence rules --------------------------------------------------------


def _is_question_only(text: str) -> bool:
    parts = [part.strip() for part in _UTTERANCE_RE.findall(text) if part.strip()]
    return bool(parts) and all(part.endswith(("?", "؟")) for part in parts)


def question_only_ids(transcript: list[TranscriptItem]) -> set[str]:
    """Segments that only ask something: a question is never evidence for a finding or a negative."""
    return {item.id for item in transcript if _is_question_only(item.text)}


def _cited(value: Any, known: set[str], questions: set[str] = frozenset()) -> list[str]:
    """Valid segment ids, or none when every cited segment is only a question."""
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        seg_id = str(item).strip()
        if seg_id in known and seg_id not in ids:
            ids.append(seg_id)
    if ids and all(seg_id in questions for seg_id in ids):
        return []
    return ids


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def clean_sentences(
    section: str,
    raw_section: Any,
    known: set[str],
    low: set[str],
    questions: set[str] = frozenset(),
) -> list[Sentence]:
    """Drop any sentence without a valid answer segment id; mark sentences citing low-confidence segments."""
    raw_sentences = raw_section.get("sentences") if isinstance(raw_section, dict) else raw_section
    sentences: list[Sentence] = []
    dropped = 0
    for item in _items(raw_sentences):
        text = str(item.get("text") or "").strip()
        ids = _cited(item.get("segment_ids"), known, questions)
        if not text or not ids:
            dropped += 1
            continue
        fields = {
            "sentence_id": f"{_SENTENCE_PREFIX[section]}-{len(sentences) + 1}",
            "text": text,
            "segment_ids": ids,
            "low_confidence": any(seg_id in low for seg_id in ids),
        }
        if section == "assessment_plan":
            part = item.get("part") if item.get("part") in ("assessment", "plan") else "plan"
            sentences.append(PlanSentence(**fields, part=part))
        else:
            sentences.append(Sentence(**fields))
    if dropped:
        logger.info(
            "Dropped unsourced sentences",
            extra={"event_type": "ambient_evidence", "section": section, "dropped": dropped},
        )
    return sentences


def enforce_evidence(raw: dict[str, Any], transcript: list[TranscriptItem], options: NoteOptions) -> DraftParts:
    known = {item.id for item in transcript}
    low = low_confidence_ids(transcript)
    questions = question_only_ids(transcript)
    by_id = {item.id: item for item in transcript}
    raw_sections = raw.get("sections") if isinstance(raw.get("sections"), dict) else {}

    sections = {
        name: clean_sentences(name, raw_sections.get(name), known, low, questions) for name in SECTION_NAMES
    }
    orders = _clean_orders(raw.get("orders"), known, questions)
    parts = DraftParts(
        sections=sections,
        diagnoses=_clean_diagnoses(raw.get("diagnoses"), known, options.patient_context, questions),
        orders=orders,
        mentions=_clean_mentions(raw.get("mentions"), known, orders, questions),
        instructions=_clean_instructions(
            raw.get("instructions"), known, options.resolved_instruction_language, questions
        ),
        flags=_build_flags(raw.get("flags"), orders, known, low, by_id),
        transcription_errors=_clean_transcription_errors(raw.get("possible_transcription_errors"), known, by_id),
    )
    texts = {item.id: item.text for item in transcript}
    parts.measured, parts.measured_evidence = asklepios.clean_record(
        raw.get("record"), texts, questions, asklepios.DRAFT_MODEL_GROUPS
    )
    _restore_heard_wording(parts)
    return parts


def _restore_heard_wording(parts: DraftParts) -> None:
    """A suspected mishearing is corrected only by the physician: put the heard words back in the note."""
    for hint in parts.transcription_errors:
        pattern = re.compile(re.escape(hint.likely), re.IGNORECASE)
        cited = set(hint.segment_ids)
        items = [*(s for sentences in parts.sections.values() for s in sentences), *parts.mentions]
        if parts.instructions is not None:
            items.append(parts.instructions)
        for item in items:
            if cited.intersection(item.segment_ids) and pattern.search(item.text):
                item.text = pattern.sub(hint.heard, item.text)


def _squash(text: str) -> str:
    return " ".join(text.lower().split())


def _clean_transcription_errors(
    value: Any,
    known: set[str],
    by_id: dict[str, TranscriptItem],
) -> list[TranscriptionErrorHint]:
    """Keep a hint only when `heard` is really in a cited segment and `likely` differs from it."""
    hints: list[TranscriptionErrorHint] = []
    seen: set[tuple[str, str]] = set()
    for item in _items(value):
        heard = str(item.get("heard") or "").strip()
        likely = str(item.get("likely") or "").strip()
        if not heard or not likely or _squash(heard) == _squash(likely):
            continue
        ids = [
            seg_id
            for seg_id in _cited(item.get("segment_ids"), known)
            if _squash(heard) in _squash(by_id[seg_id].text)
        ]
        key = (_squash(heard), _squash(likely))
        if ids and key not in seen:
            seen.add(key)
            hints.append(TranscriptionErrorHint(heard=heard, likely=likely, segment_ids=ids))
    return hints


def _clean_diagnoses(
    value: Any,
    known: set[str],
    context: PatientContext | None,
    questions: set[str] = frozenset(),
) -> list[Diagnosis]:
    chronic_context = {item.strip().lower() for item in (context.chronic_diseases if context else [])}
    diagnoses: list[Diagnosis] = []
    dropped_codes = 0
    for item in _items(value):
        ids = _cited(item.get("segment_ids"), known, questions)
        if not ids:
            continue
        raw_code = item.get("icd10")
        entry = icd10.lookup(raw_code) if raw_code else None
        if raw_code and entry is None:
            dropped_codes += 1
        label = str(item.get("label") or "").strip() or (entry.label if entry else "")
        if not label:
            continue
        diagnoses.append(
            Diagnosis(
                id=f"d{len(diagnoses) + 1}",
                icd10=entry.code if entry else None,
                label=label,
                rank="primary" if item.get("rank") == "primary" else "secondary",
                suspected=bool(item.get("suspected")),
                chronic=bool(item.get("chronic")) or label.lower() in chronic_context,
                segment_ids=ids,
            )
        )
    primaries = [dx for dx in diagnoses if dx.rank == "primary"]
    for extra in primaries[1:]:
        extra.rank = "secondary"
    if diagnoses and not primaries:
        diagnoses[0].rank = "primary"
    if dropped_codes:
        logger.info(
            "Dropped ICD-10 codes not in the local table",
            extra={"event_type": "ambient_icd10", "dropped": dropped_codes},
        )
    return diagnoses


def _iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _normalize_medication(payload: dict[str, Any]) -> None:
    """Models sometimes put "as needed" or "twice daily" in route; it is a frequency."""
    route = str(payload.get("route") or "").strip()
    if not route or not _FREQUENCY_RE.search(route):
        return
    frequency = str(payload.get("frequency") or "").strip()
    if route.lower() not in frequency.lower():
        payload["frequency"] = f"{frequency} {route}".strip() if frequency else route
    payload["route"] = None


def _clean_orders(value: Any, known: set[str], questions: set[str] = frozenset()) -> list[Order]:
    today = date.today()
    orders: list[Order] = []
    for item in _items(value):
        kind = item.get("kind")
        ids = _cited(item.get("segment_ids"), known, questions)
        if kind not in _ORDER_KINDS or not ids:
            continue
        payload = dict(item.get("payload")) if isinstance(item.get("payload"), dict) else {}
        if kind == "medication":
            _normalize_medication(payload)
        elif kind == "follow_up":
            spoken = _iso_date(payload.get("date"))
            interval = _positive_int(payload.get("interval_days"))
            target = spoken or (today + timedelta(days=interval) if interval else None)
            payload["date"] = target.isoformat() if target else None
            payload["booked"] = False
        elif kind == "sick_leave":
            days = _positive_int(payload.get("days"))
            start = _iso_date(payload.get("start_date")) or (today if days else None)
            end = _iso_date(payload.get("end_date")) or (start + timedelta(days=days - 1) if start and days else None)
            payload["start_date"] = start.isoformat() if start else None
            payload["end_date"] = end.isoformat() if end else None
            payload["confirm_required"] = True
        orders.append(Order(id=f"o{len(orders) + 1}", kind=kind, payload=payload, segment_ids=ids))
    return orders


def _clean_mentions(
    value: Any,
    known: set[str],
    orders: list[Order],
    questions: set[str] = frozenset(),
) -> list[Mention]:
    mentions: list[Mention] = []
    for item in _items(value):
        kind = item.get("kind")
        text = str(item.get("text") or "").strip()
        ids = _cited(item.get("segment_ids"), known, questions)
        if kind in _MENTION_KINDS and text and ids:
            mentions.append(Mention(kind=kind, text=text, segment_ids=ids))
    covered = {seg_id for mention in mentions if mention.kind == "sick_leave" for seg_id in mention.segment_ids}
    for order in orders:
        if order.kind == "sick_leave" and not covered.intersection(order.segment_ids):
            dates = " to ".join(str(order.payload[key]) for key in ("start_date", "end_date") if order.payload.get(key))
            mentions.append(Mention(kind="sick_leave", text=f"Sick leave {dates}".strip(), segment_ids=order.segment_ids))
    return mentions


def _clean_instructions(
    value: Any,
    known: set[str],
    language: str,
    questions: set[str] = frozenset(),
) -> Instructions:
    data = value if isinstance(value, dict) else {}
    text = str(data.get("text") or "").strip()
    ids = _cited(data.get("segment_ids"), known, questions)
    if not text or not ids:
        return Instructions(language=language)
    return Instructions(language=language, text=text, segment_ids=ids)


def _build_flags(
    value: Any,
    orders: list[Order],
    known: set[str],
    low: set[str],
    by_id: dict[str, TranscriptItem],
) -> list[Flag]:
    """Low-confidence drug names and doses. Only segments below the confidence threshold produce flags."""
    flags: list[Flag] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()

    def add(kind: str, text: Any, ids: list[str]) -> None:
        clean = str(text or "").strip()
        key = (kind, clean.lower(), tuple(ids))
        if kind in _FLAG_KINDS and clean and ids and key not in seen:
            seen.add(key)
            flags.append(Flag(kind=kind, text=clean, segment_ids=ids))

    for item in _items(value):
        ids = [seg_id for seg_id in _cited(item.get("segment_ids"), known) if seg_id in low]
        add(str(item.get("kind")), item.get("text"), ids)
    for order in orders:
        if order.kind != "medication":
            continue
        ids = [seg_id for seg_id in order.segment_ids if seg_id in low]
        add("drug_name", order.payload.get("name"), ids)
        add("dose", order.payload.get("dose"), ids)
    for seg_id in sorted(low, key=lambda item: int(item[1:]) if item[1:].isdigit() else 0):
        segment = by_id.get(seg_id)
        if segment is None:
            continue
        for match in _DOSE_RE.finditer(segment.text):
            add("dose", match.group(0), [seg_id])
    return flags


# --- soap_note via SystemDisplayPlugin ------------------------------------


def _join(sentences: list[Sentence], note_form: str) -> str:
    if note_form == "bullets":
        return "\n".join(f"- {sentence.text}" for sentence in sentences)
    return " ".join(sentence.text for sentence in sentences)


def _join_by_diagnosis(sentences: list[Sentence], note_form: str) -> str:
    """Assessment/plan sentences are "<diagnosis>: <text>"; print each diagnosis heading once."""
    groups: dict[str, list[str]] = {}
    for sentence in sentences:
        match = _PLAN_LABEL_RE.match(sentence.text)
        label, text = (match.group(1).strip(), match.group(2).strip()) if match else ("", sentence.text)
        groups.setdefault(label, []).append(text)
    blocks = []
    for label, texts in groups.items():
        if note_form == "bullets":
            body = "\n".join(f"- {text}" for text in texts)
            blocks.append(f"{label}:\n{body}" if label else body)
        else:
            body = " ".join(texts)
            blocks.append(f"{label}: {body}" if label else body)
    return ("\n\n" if note_form == "bullets" else "\n").join(blocks)


def _without_label(sentences: list[Sentence]) -> list[Sentence]:
    """Drop the routing label ("Vitals: ", "History: ") once the sentence sits under that field."""
    return [s.model_copy(update={"text": s.text.split(":", 1)[1].strip()}) for s in sentences]


def soap_source(sections: dict[str, list[Sentence]], *, note_form: str, note_language: str) -> dict[str, str]:
    """Flatten draft sections onto soap_note field names. Missing sections contribute nothing."""
    source: dict[str, str] = {}
    if "chief_complaint" in sections:
        source["ChiefComplaint"] = _join(sections["chief_complaint"], note_form)
    if "hpi" in sections:
        history = [s for s in sections["hpi"] if s.text.lower().startswith(_HISTORY_PREFIXES)]
        source["HPI"] = _join([s for s in sections["hpi"] if s not in history], note_form)
        source["MedicalHistory"] = _join(_without_label(history), note_form)
    exam_sentences = list(sections.get("physical_exam", []))
    vitals = [s for s in exam_sentences if s.text.lower().startswith(_VITALS_PREFIXES)]
    measurements = [s for s in exam_sentences if s.text.lower().startswith(_MEASUREMENT_PREFIXES)]
    if vitals or measurements:
        source["Vitals"] = _join([*_without_label(vitals), *measurements], note_form)
        exam_sentences = [s for s in exam_sentences if s not in vitals and s not in measurements]
    if "physical_exam" in sections or "review_of_systems" in sections:
        blocks = []
        exam = _join(exam_sentences, note_form)
        if exam:
            blocks.append(exam)
        ros = _join(sections.get("review_of_systems", []), note_form)
        if ros:
            blocks.append(f"{_ROS_LABEL.get(note_language, _ROS_LABEL['english'])}\n{ros}")
        source["PhysicalExamination"] = "\n\n".join(blocks)
    if "assessment_plan" in sections:
        items = sections["assessment_plan"]
        source["Assessments"] = _join_by_diagnosis(
            [s for s in items if getattr(s, "part", None) == "assessment"], note_form
        )
        source["TreatmentPlans"] = _join_by_diagnosis(
            [s for s in items if getattr(s, "part", None) == "plan"], note_form
        )
    return {name: text for name, text in source.items() if text}


def soap_note_decoder(field_names: tuple[str, ...]) -> dict[str, Any]:
    """Inline SystemDisplayPlugin decoder: direct copies only, so reshape never rewrites sourced text."""
    return {
        "view_id": "soap_note",
        "view_name": "SOAP Note",
        "fields": [
            {"field_name": name, "field_type": "string", "source_path": name, "transform": "direct", "required": False}
            for name in field_names
        ],
    }


# --- Asklepios record ------------------------------------------------------

_HISTORY_LABEL = {"english": "History:", "arabic": "التاريخ المرضي:"}


def _ids(sentences: list[Sentence]) -> list[str]:
    ordered: list[str] = []
    for sentence in sentences:
        for seg_id in sentence.segment_ids:
            if seg_id not in ordered:
                ordered.append(seg_id)
    return ordered


def _text_fields(
    sections: dict[str, list[Sentence]], options: NoteOptions
) -> tuple[dict[str, dict[str, str | None]], dict[str, list[str]]]:
    """Free-text record fields, taken from the same sentences (and the same text) as soap_note.

    Only fields whose section is present are returned, so a one-section regenerate never touches the rest.
    """
    source = soap_source(sections, note_form=options.note_form, note_language=options.note_language)
    values: dict[str, dict[str, str | None]] = {}
    evidence: dict[str, list[str]] = {}

    def put(group: str, name: str, text: str | None, ids: list[str]) -> None:
        values.setdefault(group, {})[name] = text or None
        if text:
            evidence[f"{group}.{name}"] = ids

    if "chief_complaint" in sections:
        ids = _ids(sections["chief_complaint"])
        put("clinical_visit", "chiefComplaint", source.get("ChiefComplaint"), ids)
        put("nursing_assessment", "reasonOfVisit", " ".join(s.text for s in sections["chief_complaint"]), ids)
    if "hpi" in sections:
        history = source.get("MedicalHistory")
        label = _HISTORY_LABEL.get(options.note_language, "History:")
        text = "\n".join(part for part in (source.get("HPI"), f"{label} {history}" if history else None) if part)
        put("clinical_visit", "historyOfPresentIllness", text, _ids(sections["hpi"]))
    if "physical_exam" in sections or "review_of_systems" in sections:
        exam = [
            s
            for s in sections.get("physical_exam", [])
            if not s.text.lower().startswith(_VITALS_PREFIXES + _MEASUREMENT_PREFIXES)
        ]
        ids = _ids([*exam, *sections.get("review_of_systems", [])])
        put("clinical_visit", "physicalExaminationSummery", source.get("PhysicalExamination"), ids)
    if "assessment_plan" in sections:
        items = sections["assessment_plan"]
        put("assessment", "assessment", source.get("Assessments"), _ids([s for s in items if s.part == "assessment"]))
        put("plan_of_care", "treatmentPlan", source.get("TreatmentPlans"), _ids([s for s in items if s.part == "plan"]))
    return values, evidence


def _conditions(options: NoteOptions) -> str | None:
    chronic = options.patient_context.chronic_diseases if options.patient_context else []
    return ", ".join(chronic) or None


def _diagnosis_rows(diagnoses: list[Diagnosis]) -> list[dict[str, Any]]:
    return [{"rank": dx.rank, "suspected": dx.suspected, "segment_ids": dx.segment_ids} for dx in diagnoses]


def record_for_draft(parts: DraftParts, options: NoteOptions) -> asklepios.Record:
    """Measured fields (vitals, measurements, pain, nursing) from the model, text fields from the note sections."""
    values = {group: dict(fields) for group, fields in parts.measured.items()}
    evidence = dict(parts.measured_evidence)
    text_values, text_evidence = _text_fields(parts.sections, options)
    for group, fields in text_values.items():
        for name, text in fields.items():
            if text:
                values.setdefault(group, {})[name] = text
    evidence.update(text_evidence)
    return asklepios.assemble(
        values,
        evidence,
        patient_id=options.patient_id,
        encounter_id=options.encounter_id,
        patient_conditions=_conditions(options),
        diagnoses=_diagnosis_rows(parts.diagnoses),
    )


def record_for_section(parts: DraftParts, options: NoteOptions, section: str) -> asklepios.Record:
    """Only the record keys this section decides."""
    values, evidence = _text_fields(parts.sections, options)
    diagnoses = _diagnosis_rows(parts.diagnoses) if section == "assessment_plan" else None
    groups = set(values) | ({"patient_diagnosis"} if diagnoses is not None else set())
    return asklepios.assemble(
        values,
        evidence,
        patient_id=options.patient_id,
        encounter_id=options.encounter_id,
        groups=groups,
        diagnoses=diagnoses,
        sparse=True,
    )
