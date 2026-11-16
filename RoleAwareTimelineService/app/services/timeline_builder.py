"""Deterministic timeline cleanup: backfill, merge, sort, and ids."""
import re
from datetime import datetime
from typing import Dict, List, Sequence

from app.ai.guardrails import (
    clean_text,
    input_corpus,
    is_high_risk_medication,
    medication_is_active,
    strip_vital_units,
)
from app.models.schemas import TimelineEvent, TimelineEventDraft


def parse_date(value: str) -> datetime:
    """Parse an ISO-like date. Unparsed values sort after real dates."""
    normalized = (value or "").strip()
    if not normalized:
        return datetime.max
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(normalized, pattern)
        except ValueError:
            continue
    return datetime.max


def normalize_key(value: str) -> str:
    """Normalize text for duplicate detection."""
    lowered = value.casefold()
    cleaned = re.sub(r"[^a-z0-9/]+", " ", lowered)
    return " ".join(cleaned.split())


def project_chart(patient: Dict[str, object]) -> List[TimelineEvent]:
    """Build factual events for structured input the model did not already return."""
    events: List[TimelineEvent] = []
    events.extend(_diagnosis_events(patient.get("diagnoses") or []))
    events.extend(_medication_events(patient.get("medications") or []))
    events.extend(_lab_events(patient.get("lab_results") or []))
    events.extend(_vital_events(patient.get("vitals") or []))
    events.extend(_procedure_events(patient.get("procedures") or []))
    events.extend(_encounter_events(patient.get("encounters") or []))
    events.extend(_note_events(patient.get("notes") or []))
    events.extend(_allergy_events(patient.get("allergies") or []))
    return events


def clean_drafts(drafts: Sequence[TimelineEventDraft], patient: Dict[str, object]) -> List[TimelineEvent]:
    """Remove invented units and interpretations from model events."""
    corpus = input_corpus(patient)
    vital_values = " ".join(str(item.get("value", "")) for item in (patient.get("vitals") or []))
    cleaned: List[TimelineEvent] = []
    for index, draft in enumerate(drafts, start=1):
        title = clean_text(draft.title, corpus)
        description = clean_text(draft.description, corpus)
        if draft.event_type == "vital":
            title = strip_vital_units(title, vital_values)
            description = strip_vital_units(description, vital_values)
        if not description and title:
            description = title
        if not title and description:
            title = description[:120]
        if not title or not description:
            continue
        cleaned.append(
            TimelineEvent(
                event_id=f"tmp-{index:03d}",
                date=draft.date,
                event_type=draft.event_type,
                title=title,
                description=description,
                clinical_importance=draft.clinical_importance,
                source=draft.source,
            )
        )
    return cleaned


def backfill_missing(events: Sequence[TimelineEvent], patient: Dict[str, object]) -> List[TimelineEvent]:
    """Add input facts the timeline model omitted. Do not add interpretations."""
    present = list(events)
    for candidate in project_chart(patient):
        if _already_covered(present, candidate, patient):
            continue
        present.append(candidate)
    return present


def merge_events(events: Sequence[TimelineEvent]) -> List[TimelineEvent]:
    """Merge obvious duplicates. Keep both events when the descriptions disagree."""
    merged: List[TimelineEvent] = []
    index_by_key: Dict[tuple, int] = {}
    for event in events:
        key = (event.date.strip(), event.event_type, normalize_key(event.title))
        existing_index = index_by_key.get(key)
        if existing_index is None:
            index_by_key[key] = len(merged)
            merged.append(event)
            continue
        current = merged[existing_index]
        if not _descriptions_compatible(current.description, event.description):
            merged.append(event)
            continue
        merged[existing_index] = current.model_copy(
            update={
                "title": _longer(current.title, event.title),
                "description": _longer(current.description, event.description),
                "source": _merge_sources(current.source, event.source),
                "clinical_importance": _higher_importance(
                    current.clinical_importance,
                    event.clinical_importance,
                ),
            }
        )
    return merged


def sort_events(events: Sequence[TimelineEvent]) -> List[TimelineEvent]:
    """Sort events by date, then type, then title."""
    return sorted(
        events,
        key=lambda event: (parse_date(event.date), event.event_type, event.title.lower()),
    )


def assign_ids(events: Sequence[TimelineEvent]) -> List[TimelineEvent]:
    """Assign stable ids after the final sort."""
    assigned = []
    for index, event in enumerate(events, start=1):
        assigned.append(event.model_copy(update={"event_id": f"evt-{index:03d}"}))
    return assigned


def _already_covered(events: Sequence[TimelineEvent], candidate: TimelineEvent, patient: Dict[str, object]) -> bool:
    needles = _coverage_needles(candidate)
    for event in events:
        if event.event_type != candidate.event_type or event.date != candidate.date:
            continue
        blob = f"{event.title} {event.description}".casefold()
        if all(needle.casefold() in blob for needle in needles):
            return True
    note_text = candidate.description.casefold().strip().rstrip(".")
    if candidate.source == "notes" and note_text:
        for event in events:
            blob = f"{event.title} {event.description}".casefold()
            if note_text in blob or blob in note_text:
                return True
    return False


def _coverage_needles(candidate: TimelineEvent) -> List[str]:
    if candidate.event_type == "lab":
        tokens = candidate.title.split()
        name = tokens[0] if tokens else candidate.title
        value_match = re.search(r"\d+(?:\.\d+)?", candidate.description)
        needles = [name]
        if value_match:
            needles.append(value_match.group(0))
        return needles
    if candidate.event_type == "vital":
        value_match = re.search(r"\d+(?:/\d+)?", candidate.description)
        return [value_match.group(0)] if value_match else [candidate.title]
    if candidate.event_type in {"diagnosis", "medication", "procedure", "allergy"}:
        name = candidate.title
        if candidate.event_type == "allergy":
            name = re.sub(r"\s+allergy$", "", name, flags=re.IGNORECASE)
        return [name]
    if candidate.event_type == "admission":
        return ["admission"] if "admission" in candidate.description.casefold() else [candidate.title]
    return [candidate.title]


def _diagnosis_events(rows: Sequence[Dict[str, object]]) -> List[TimelineEvent]:
    return [
        _event(
            date=str(row["date"]),
            event_type="diagnosis",
            title=str(row["name"]),
            description=f"{row['name']} diagnosed on {row['date']}.",
            importance="medium",
            source="diagnoses",
        )
        for row in rows
    ]


def _medication_events(rows: Sequence[Dict[str, object]]) -> List[TimelineEvent]:
    events = []
    for row in rows:
        name = str(row["name"])
        description = f"{name} started on {row['start_date']}"
        status = row.get("status")
        if status:
            description += f", status {status}"
        if row.get("end_date"):
            description += f", end date {row['end_date']}"
        description += "."
        stopped = not medication_is_active(row)
        importance = "high" if is_high_risk_medication(name) or stopped else "medium"
        events.append(
            _event(
                date=str(row["start_date"]),
                event_type="medication",
                title=name,
                description=description,
                importance=importance,
                source="medications",
            )
        )
    return events


def _lab_events(rows: Sequence[Dict[str, object]]) -> List[TimelineEvent]:
    events = []
    for row in rows:
        unit = str(row.get("unit") or "").strip()
        measurement = f"{row['value']} {unit}".strip() if unit else str(row["value"])
        description = f"{row['name']} {measurement}"
        flag = str(row.get("flag") or "").strip()
        if flag:
            description += f", flagged {flag}"
        description += f", on {row['date']}."
        events.append(
            _event(
                date=str(row["date"]),
                event_type="lab",
                title=f"{row['name']} {measurement}",
                description=description,
                importance="high" if flag else "medium",
                source="lab_results",
            )
        )
    return events


def _vital_events(rows: Sequence[Dict[str, object]]) -> List[TimelineEvent]:
    return [
        _event(
            date=str(row["date"]),
            event_type="vital",
            title=f"{row['name']} {row['value']}",
            description=f"{row['name']} {row['value']} on {row['date']}.",
            importance="high",
            source="vitals",
        )
        for row in rows
    ]


def _procedure_events(rows: Sequence[Dict[str, object]]) -> List[TimelineEvent]:
    events = []
    for row in rows:
        status = str(row.get("status") or "").strip()
        description = f"{row['name']} {status} on {row['date']}.".replace("  ", " ")
        events.append(
            _event(
                date=str(row["date"]),
                event_type="procedure",
                title=str(row["name"]),
                description=description,
                importance="medium",
                source="procedures",
            )
        )
    return events


def _encounter_events(rows: Sequence[Dict[str, object]]) -> List[TimelineEvent]:
    events = []
    for row in rows:
        reason = str(row.get("reason") or "").strip()
        label = str(row["type"]).strip()
        title = f"{label[:1].upper()}{label[1:]} for {reason}" if reason else label
        description = f"{title} on {row['date']}."
        events.append(
            _event(
                date=str(row["date"]),
                event_type="admission",
                title=title,
                description=description,
                importance="high",
                source="encounters",
            )
        )
    return events


def _note_events(rows: Sequence[Dict[str, object]]) -> List[TimelineEvent]:
    events = []
    for row in rows:
        text = str(row["text"]).strip()
        title = text.rstrip(".")
        if len(title) > 120:
            title = title[:117].rstrip() + "..."
        events.append(
            _event(
                date=str(row["date"]),
                event_type="symptom",
                title=title,
                description=text if text.endswith(".") else f"{text}.",
                importance="high",
                source="notes",
            )
        )
    return events


def _allergy_events(rows: Sequence[Dict[str, object]]) -> List[TimelineEvent]:
    return [
        _event(
            date=str(row["date"]),
            event_type="allergy",
            title=f"{row['name']} allergy",
            description=f"{row['name']} allergy recorded on {row['date']}.",
            importance="high",
            source="allergies",
        )
        for row in rows
    ]


def _event(
    date: str,
    event_type: str,
    title: str,
    description: str,
    importance: str,
    source: str,
) -> TimelineEvent:
    return TimelineEvent(
        event_id="pending",
        date=date,
        event_type=event_type,
        title=title,
        description=description,
        clinical_importance=importance,
        source=source,
    )


def _descriptions_compatible(left: str, right: str) -> bool:
    normalized_left = normalize_key(left)
    normalized_right = normalize_key(right)
    if not normalized_left or not normalized_right:
        return True
    return (
        normalized_left == normalized_right
        or normalized_left in normalized_right
        or normalized_right in normalized_left
    )


def _longer(left: str, right: str) -> str:
    return right if len(right.strip()) > len(left.strip()) else left


def _merge_sources(left: str, right: str) -> str:
    parts = []
    for value in (left, right):
        parts.extend(part.strip() for part in value.split(",") if part.strip())
    return ", ".join(sorted(set(parts)))


def _higher_importance(left: str, right: str) -> str:
    ranking = {"high": 3, "medium": 2, "low": 1}
    return left if ranking[left] >= ranking[right] else right
