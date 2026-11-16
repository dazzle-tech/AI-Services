"""Fidelity checks applied after each model step."""
import json
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.models.schemas import RoleHighlight, TimelineEvent

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_MMHG = re.compile(r"\s*mm\s*Hg\b", re.IGNORECASE)
_FALSE_REASSURANCE = re.compile(
    r"\b(takes none|takes no|no medications|no known|denies|within normal|is normal|are normal|unremarkable)\b",
    re.IGNORECASE,
)
_DROP_IF_UNSUPPORTED = (
    re.compile(r"\b(infarcts?|myocardial infarction|stemi|nstemi)\b", re.IGNORECASE),
    re.compile(r"\b(rising|rises|rise|falling|falls|fall|trending|trend)\b", re.IGNORECASE),
    re.compile(r"\b(occlusion|stenosis|patent)\b", re.IGNORECASE),
    re.compile(
        r"\b(lad|rca|lcx|circumflex|left anterior descending|right coronary)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bcontrast allergy\b", re.IGNORECASE),
    re.compile(
        r"\b(recommend|should order|hold metformin|change the dose|start heparin)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|units?|iu)\b", re.IGNORECASE),
    re.compile(
        r"\b(subcutaneous|intravenous|intramuscular|twice daily|once daily|by mouth|orally|bid|tid|qid)\b",
        re.IGNORECASE,
    ),
)
_HIGH_RISK_TERMS = (
    "insulin",
    "heparin",
    "enoxaparin",
    "warfarin",
    "apixaban",
    "rivaroxaban",
    "dabigatran",
    "edoxaban",
    "fondaparinux",
    "morphine",
    "fentanyl",
    "oxycodone",
    "hydrocodone",
    "hydromorphone",
    "methadone",
    "tramadol",
    "codeine",
    "opioid",
    "anticoagulant",
)
_ANTITHROMBOTIC_TERMS = (
    "aspirin",
    "clopidogrel",
    "plavix",
    "heparin",
    "enoxaparin",
    "warfarin",
    "apixaban",
    "rivaroxaban",
    "dabigatran",
    "edoxaban",
    "ticagrelor",
    "prasugrel",
    "anticoagulant",
    "antithrombotic",
)
_VITAL_REST = (
    ("heart rate", (r"\bheart rate\b", r"\bpulse\b")),
    ("respiratory rate", (r"\brespiratory rate\b",)),
    ("temperature", (r"\btemperature\b",)),
    ("oxygen saturation", (r"\boxygen saturation\b", r"\bspo2\b", r"\bo2 sat\b")),
)


def split_sentences(text: str) -> List[str]:
    """Split prose on sentence boundaries."""
    stripped = (text or "").strip()
    if not stripped:
        return []
    return [part.strip() for part in _SENTENCE_SPLIT.split(stripped) if part.strip()]


def clean_text(text: str, corpus: str) -> str:
    """Remove units and sentences that add facts absent from the allowed corpus."""
    cleaned = text or ""
    if not re.search(r"mm\s*hg", corpus or "", flags=re.IGNORECASE):
        cleaned = _MMHG.sub("", cleaned)
    kept: List[str] = []
    for sentence in split_sentences(cleaned):
        if any(pattern.search(sentence) and not pattern.search(corpus or "") for pattern in _DROP_IF_UNSUPPORTED):
            continue
        kept.append(sentence.strip())
    return " ".join(kept).strip()


def strip_vital_units(text: str, recorded_value: str) -> str:
    """Keep a vital value as recorded. Do not append mmHg."""
    if re.search(r"mm\s*hg", recorded_value or "", flags=re.IGNORECASE):
        return text
    return _MMHG.sub("", text or "").strip()


def timeline_corpus(events: Sequence[TimelineEvent], age: Optional[str], gender: Optional[str]) -> str:
    """Corpus the summary and highlights are allowed to restate."""
    parts = [f"{event.title} {event.description} {event.source}" for event in events]
    if age:
        parts.append(age)
    if gender:
        parts.append(gender)
    return "\n".join(parts)


def input_corpus(patient: Dict[str, object]) -> str:
    """Serialize the chart extract for fidelity checks."""
    return json.dumps(patient, ensure_ascii=True)


def prepare_highlights(
    highlights: Sequence[RoleHighlight],
    events: Sequence[TimelineEvent],
    viewer_role: str,
    corpus: str,
) -> Tuple[List[RoleHighlight], List[str]]:
    """Drop unsupported highlights, demote old nurse procedures, and lead with salience."""
    events_by_id = {event.event_id: event for event in events}
    moved_gaps: List[str] = []
    prepared: List[RoleHighlight] = []

    for item in highlights:
        event = events_by_id.get(item.event_id)
        if event is None:
            if "not documented" in item.why_it_matters.lower():
                moved_gaps.append(item.why_it_matters)
            continue
        why = _scrub_why(item.why_it_matters, event, corpus)
        if not why:
            continue
        salience = item.salience
        if viewer_role == "nurse" and is_history_procedure(event, events):
            salience = "context"
        prepared.append(item.model_copy(update={"why_it_matters": why, "salience": salience}))

    deduped = _dedupe_highlights(prepared)
    leads = [item for item in deduped if item.salience == "lead"]
    context = [item for item in deduped if item.salience == "context"]
    return leads + context, moved_gaps


def is_history_procedure(event: TimelineEvent, events: Sequence[TimelineEvent]) -> bool:
    """Old procedures stay in the history unless tied to a device, wound, or bleeding precaution."""
    if event.event_type != "procedure":
        return False
    blob = f"{event.title} {event.description}".lower()
    if any(token in blob for token in ("device", "wound", "bleeding")):
        return False
    anchors = [other.date for other in events if other.event_type in {"admission", "symptom"} and other.date]
    if not anchors:
        return True
    from app.services.timeline_builder import parse_date

    procedure_date = parse_date(event.date)
    latest_anchor = max(parse_date(anchor) for anchor in anchors)
    from datetime import datetime

    if procedure_date == datetime.max:
        return True
    return procedure_date < latest_anchor


def combine_gaps(model_gaps: Iterable[str], patient: Dict[str, object], viewer_role: str) -> List[str]:
    """Merge model gaps with the role facts that are absent from the chart."""
    ordered: List[str] = []
    seen = set()
    for item in list(required_gaps(patient, viewer_role)) + list(model_gaps):
        text = " ".join(str(item).split())
        if not text or not acceptable_gap(text):
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(text)
    return ordered


def acceptable_gap(text: str) -> bool:
    """A gap names a missing fact. It does not convert the gap into a normal finding."""
    return _FALSE_REASSURANCE.search(text) is None


def required_gaps(patient: Dict[str, object], viewer_role: str) -> List[str]:
    """Role-relevant facts the chart does not contain."""
    if viewer_role == "nurse":
        return _nurse_gaps(patient)
    if viewer_role == "radiologist":
        return _radiologist_gaps(patient)
    if viewer_role == "cardiologist":
        return _cardiologist_gaps(patient)
    return []


def medication_is_active(medication: Dict[str, object]) -> bool:
    """Treat a listed medicine as active unless the chart says it stopped."""
    status = str(medication.get("status") or "").strip().lower()
    if status in {"stopped", "discontinued", "inactive", "completed"}:
        return False
    if medication.get("end_date"):
        return False
    return True


def is_high_risk_medication(name: str) -> bool:
    """Insulin, anticoagulants, and opioids are the nurse high-risk set."""
    lowered = name.lower()
    return any(term in lowered for term in _HIGH_RISK_TERMS)


def _scrub_why(why: str, event: TimelineEvent, corpus: str) -> str:
    cleaned = clean_text(why, corpus)
    event_blob = f"{event.title} {event.description}".lower()
    if "penicillin" in event_blob and "contrast" in cleaned.lower():
        kept = [sentence for sentence in split_sentences(cleaned) if "contrast" not in sentence.lower()]
        cleaned = " ".join(kept).strip()
    if "penicillin" in event_blob and not cleaned:
        cleaned = "Penicillin allergy is recorded."
    return cleaned


def _dedupe_highlights(highlights: Sequence[RoleHighlight]) -> List[RoleHighlight]:
    rank = {"lead": 2, "context": 1}
    chosen: Dict[str, RoleHighlight] = {}
    order: List[str] = []
    for item in highlights:
        existing = chosen.get(item.event_id)
        if existing is None:
            chosen[item.event_id] = item
            order.append(item.event_id)
            continue
        if rank[item.salience] > rank[existing.salience]:
            chosen[item.event_id] = item
    return [chosen[event_id] for event_id in order]


def _nurse_gaps(patient: Dict[str, object]) -> List[str]:
    gaps: List[str] = []
    vital_text = json.dumps(
        {"vitals": patient.get("vitals") or [], "notes": patient.get("notes") or []},
        ensure_ascii=True,
    )
    missing = [label for label, patterns in _VITAL_REST if not any(re.search(pattern, vital_text, re.I) for pattern in patterns)]
    if missing:
        gaps.append("The rest of the vital set is not documented: " + ", ".join(missing) + ".")
    if _insulin_is_active(patient) and not _has_glucose(patient):
        gaps.append("Glucose is not documented.")
    medication_text = json.dumps(patient.get("medications") or [], ensure_ascii=True)
    if not re.search(r"\bdose\b|\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|units?|iu)\b", medication_text, re.I):
        gaps.append("Dose is not documented.")
    if not re.search(
        r"\b(route|oral|orally|subcutaneous|intravenous|intramuscular|by mouth|im|po|sq)\b",
        medication_text,
        re.I,
    ):
        gaps.append("Route is not documented.")
    if not re.search(r"\b(frequency|daily|bid|tid|qid|qhs|prn|twice|once a day|every)\b", medication_text, re.I):
        gaps.append("Frequency is not documented.")
    return gaps


def _radiologist_gaps(patient: Dict[str, object]) -> List[str]:
    chart = json.dumps(patient, ensure_ascii=True)
    order_text = json.dumps(
        {"encounters": patient.get("encounters") or [], "notes": patient.get("notes") or []},
        ensure_ascii=True,
    )
    gaps: List[str] = []
    if not re.search(
        r"\b(ct|mri|x-ray|xray|ultrasound|radiograph)\b|\bstudy ordered\b|\bimaging ordered\b",
        order_text,
        re.I,
    ):
        gaps.append("The study ordered is not documented.")
    if not re.search(r"\b(creatinine|egfr|gfr)\b", chart, re.I):
        gaps.append("Renal function (creatinine or eGFR) is not documented.")
    if not re.search(r"\bcontrast\b", chart, re.I):
        gaps.append("Contrast reaction is not documented.")
    if not re.search(r"\b(impression|radiology report|imaging report)\b", chart, re.I):
        gaps.append("Prior imaging report is not documented.")
    if not re.search(r"\b(finding|findings)\b", chart, re.I):
        gaps.append("Procedure findings are not documented.")
    return gaps


def _cardiologist_gaps(patient: Dict[str, object]) -> List[str]:
    chart = json.dumps(patient, ensure_ascii=True)
    labs = patient.get("lab_results") or []
    medications = patient.get("medications") or []
    procedures = patient.get("procedures") or []
    gaps: List[str] = []
    if not re.search(r"\b(ecg|ekg|electrocardiogram)\b", chart, re.I):
        gaps.append("ECG is not documented.")
    troponin_count = sum(1 for lab in labs if "troponin" in str(lab.get("name", "")).lower())
    if troponin_count < 2:
        gaps.append("A second troponin is not documented.")
    if troponin_count >= 1 and not re.search(r"\b(reference range|normal range|ref range)\b", chart, re.I):
        gaps.append("The troponin reference range is not documented.")
    medication_names = " ".join(str(item.get("name", "")) for item in medications).lower()
    if not any(term in medication_names for term in _ANTITHROMBOTIC_TERMS):
        gaps.append("Antithrombotic therapy is not documented.")
    angio_text = json.dumps(
        [item for item in procedures if re.search(r"angiogra", str(item.get("name", "")), re.I)],
        ensure_ascii=True,
    )
    if not re.search(r"\b(finding|findings|stenosis|occlusion|patent)\b", angio_text, re.I):
        gaps.append("Angiogram findings are not documented.")
    return gaps


def _insulin_is_active(patient: Dict[str, object]) -> bool:
    for medication in patient.get("medications") or []:
        if "insulin" in str(medication.get("name", "")).lower() and medication_is_active(medication):
            return True
    return False


def _has_glucose(patient: Dict[str, object]) -> bool:
    text = json.dumps(
        {
            "lab_results": patient.get("lab_results") or [],
            "vitals": patient.get("vitals") or [],
            "notes": patient.get("notes") or [],
        },
        ensure_ascii=True,
    )
    return re.search(r"\b(glucose|blood sugar|fingerstick)\b", text, re.I) is not None
