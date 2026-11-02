"""Identity document field extraction from OCR text.

Strategy:
1) Prefer MRZ parsing (high precision, layout-independent) when present.
2) Fallback to label-based extraction from the visual inspection zone.
3) Optionally allow an LLM fallback (existing parsing_service) to fill gaps,
   but always validate/normalize the output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import re

from app.services.mrz_parser import MRZParseResult, parse_mrz


def _clean_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _parse_visual_date(raw: str) -> str | None:
    raw = raw.strip()
    raw = raw.replace("O", "0")  # common OCR issue in dates
    raw = re.sub(r"[^\d/\-\.]", "", raw)
    if not raw:
        return None

    candidates: list[str] = []
    # yyyy-mm-dd, yyyy/mm/dd, yyyy.mm.dd
    candidates.extend(re.findall(r"\b(\d{4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})\b", raw))
    for y, m, d in candidates:
        try:
            return date(int(y), int(m), int(d)).isoformat()
        except ValueError:
            pass

    # dd-mm-yyyy, dd/mm/yyyy, dd.mm.yyyy
    for d, m, y in re.findall(r"\b(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})\b", raw):
        try:
            return date(int(y), int(m), int(d)).isoformat()
        except ValueError:
            pass

    # dd-mm-yy (assume 1900/2000; prefer age 0-120)
    for d, m, yy in re.findall(r"\b(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2})\b", raw):
        dd = int(d)
        mm = int(m)
        y2 = int(yy)
        for century in (2000, 1900):
            try:
                dt = date(century + y2, mm, dd)
            except ValueError:
                continue
            today = date.today()
            age = today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
            if 0 <= age <= 120:
                return dt.isoformat()
    return None


def _extract_labeled_value_with_indices(
    lines: list[str],
    label_patterns: list[re.Pattern[str]],
) -> tuple[str | None, list[int]]:
    for idx, line in enumerate(lines):
        raw = line.strip()
        if not raw:
            continue

        for pat in label_patterns:
            m = pat.search(raw)
            if not m:
                continue
            value = (m.group("value") or "").strip()
            if value:
                return _clean_spaces(value), [idx]
            # label-only; use next non-empty line
            for j in range(idx + 1, min(idx + 4, len(lines))):
                nxt = lines[j].strip()
                if nxt:
                    return _clean_spaces(nxt), [idx, j]
    return None, []


def _extract_labeled_value(lines: list[str], label_patterns: list[re.Pattern[str]]) -> str | None:
    value, _ = _extract_labeled_value_with_indices(lines, label_patterns)
    return value


def _merge_indices(*groups: list[int]) -> list[int]:
    seen: set[int] = set()
    merged: list[int] = []
    for group in groups:
        for idx in group:
            if idx in seen:
                continue
            seen.add(idx)
            merged.append(idx)
    return merged


def _extract_gender(lines: list[str]) -> tuple[str | None, list[int]]:
    patterns = [
        re.compile(r"(?i)\b(?:sex|gender)\b\s*[:\-]?\s*(?P<value>M|F|MALE|FEMALE|X|UNSPECIFIED)\b"),
        re.compile(r"(?i)\b(?:sex|gender)\b\s*[:\-]?\s*(?P<value>)$"),
    ]
    v, indices = _extract_labeled_value_with_indices(lines, patterns)
    if not v:
        return None, []
    v = v.upper()
    if v in ("M", "MALE"):
        return "male", indices
    if v in ("F", "FEMALE"):
        return "female", indices
    if v in ("X", "UNSPECIFIED"):
        return "unspecified", indices
    return None, []


def _extract_document_number(lines: list[str]) -> tuple[str | None, list[int]]:
    patterns = [
        re.compile(r"(?i)\b(?:passport|document|doc|id|card)\s*(?:no|number|#)\b\s*[:\-]?\s*(?P<value>[A-Z0-9<]{5,20})"),
        re.compile(r"(?i)\b(?:passport)\b\s*[:\-]?\s*(?P<value>[A-Z0-9<]{5,20})"),
        re.compile(r"(?i)\b(?:passport|document|doc|id|card)\s*(?:no|number|#)\b\s*[:\-]?\s*(?P<value>)$"),
        re.compile(r"(?i)\b(?:passport)\b\s*[:\-]?\s*(?P<value>)$"),
    ]
    v, indices = _extract_labeled_value_with_indices(lines, patterns)
    if not v:
        return None, []
    v = v.replace("<", "").strip()
    v = re.sub(r"[^A-Z0-9]", "", v.upper())
    return (v, indices) if v else (None, [])


def _extract_nationality(lines: list[str]) -> tuple[str | None, list[int]]:
    patterns = [
        re.compile(r"(?i)\bnationality\b\s*[:\-]?\s*(?P<value>[A-Z][A-Z \-]{2,})"),
        re.compile(r"(?i)\bnation(?:ality)?\b\s*[:\-]?\s*(?P<value>[A-Z][A-Z \-]{2,})"),
        re.compile(r"(?i)\bnationality\b\s*[:\-]?\s*(?P<value>)$"),
        re.compile(r"(?i)\bnation(?:ality)?\b\s*[:\-]?\s*(?P<value>)$"),
    ]
    v, indices = _extract_labeled_value_with_indices(lines, patterns)
    if not v:
        return None, []
    cleaned = re.sub(r"[^A-Z \-]", "", v.upper()).strip()
    return (cleaned, indices) if cleaned else (None, [])


def _extract_dob(lines: list[str]) -> tuple[str | None, list[int]]:
    patterns = [
        re.compile(r"(?i)\b(?:date\s*of\s*birth|birth\s*date|dob)\b\s*[:\-]?\s*(?P<value>.*)$"),
    ]
    v, indices = _extract_labeled_value_with_indices(lines, patterns)
    if not v:
        return None, []
    parsed = _parse_visual_date(v)
    return (parsed, indices) if parsed else (None, [])


def _extract_full_name(lines: list[str]) -> tuple[str | None, list[int]]:
    patterns = [
        re.compile(r"(?i)\bfull\s*name\b\s*[:\-]?\s*(?P<value>.*)$"),
        re.compile(r"(?i)\bname\b\s*[:\-]?\s*(?P<value>.*)$"),
    ]
    v, indices = _extract_labeled_value_with_indices(lines, patterns)
    if v and len(v) >= 2:
        return v, indices

    # Try combining "Surname/Family Name" + "Given Names"
    surname, surname_indices = _extract_labeled_value_with_indices(
        lines,
        [
            re.compile(r"(?i)\b(?:surname|family\s*name|last\s*name)\b\s*[:\-]?\s*(?P<value>.*)$"),
        ],
    )
    given, given_indices = _extract_labeled_value_with_indices(
        lines,
        [
            re.compile(r"(?i)\b(?:given\s*names?|first\s*name)\b\s*[:\-]?\s*(?P<value>.*)$"),
        ],
    )
    combined = " ".join(p for p in [surname, given] if p)
    if not combined:
        return None, []
    return combined, _merge_indices(surname_indices, given_indices)


@dataclass(frozen=True)
class IdentityExtraction:
    full_name: str | None
    date_of_birth: str | None
    gender: str | None
    nationality: str | None
    document_number: str | None
    document_type: str
    extraction_source: str
    mrz_present: bool
    mrz_valid: bool | None
    field_sources: dict[str, tuple[int, ...]] = field(default_factory=dict)
    field_source_kinds: dict[str, str] = field(default_factory=dict)
    visual_values: dict[str, str | None] = field(default_factory=dict)


def _indexed_clean_lines(text_lines: list[str]) -> tuple[list[str], list[int]]:
    clean_lines: list[str] = []
    origins: list[int] = []
    for index, line in enumerate(text_lines):
        if line and str(line).strip():
            clean_lines.append(_clean_spaces(str(line)))
            origins.append(index)
    return clean_lines, origins


def _to_original(indices: list[int], origins: list[int]) -> tuple[int, ...]:
    mapped: list[int] = []
    for index in indices:
        if 0 <= index < len(origins):
            mapped.append(origins[index])
    return tuple(mapped)


def _choose_field(
    visual_value: str | None,
    visual_indices: list[int],
    mrz_value: str | None,
    mrz_indices: tuple[int, ...],
    *,
    use_mrz: bool,
    origins: list[int],
) -> tuple[str | None, tuple[int, ...], str]:
    if use_mrz and mrz_value:
        return mrz_value, mrz_indices, "mrz"
    if visual_value:
        return visual_value, _to_original(visual_indices, origins), "visual"
    if mrz_value:
        return mrz_value, mrz_indices, "mrz"
    return None, (), "visual"


def extract_identity(text_lines: list[str]) -> tuple[IdentityExtraction, MRZParseResult | None]:
    clean_lines, origins = _indexed_clean_lines(text_lines)
    mrz = parse_mrz(text_lines)
    mrz_indices = mrz.source_line_indices if mrz is not None else ()

    visual_name, visual_name_idx = _extract_full_name(clean_lines)
    visual_dob, visual_dob_idx = _extract_dob(clean_lines)
    visual_gender, visual_gender_idx = _extract_gender(clean_lines)
    visual_nationality, visual_nationality_idx = _extract_nationality(clean_lines)
    visual_document, visual_document_idx = _extract_document_number(clean_lines)
    visual = {
        "full_name": visual_name,
        "date_of_birth": visual_dob,
        "gender": visual_gender,
        "nationality": visual_nationality,
        "document_number": visual_document,
    }
    visual_indices = {
        "full_name": visual_name_idx,
        "date_of_birth": visual_dob_idx,
        "gender": visual_gender_idx,
        "nationality": visual_nationality_idx,
        "document_number": visual_document_idx,
    }

    if mrz is None:
        field_sources = {
            name: _to_original(visual_indices[name], origins) if visual[name] else ()
            for name in visual
        }
        field_source_kinds = {name: "visual" for name in visual}
        return (
            IdentityExtraction(
                full_name=visual["full_name"],
                date_of_birth=visual["date_of_birth"],
                gender=visual["gender"],
                nationality=visual["nationality"],
                document_number=visual["document_number"],
                document_type="unknown",
                extraction_source="visual",
                mrz_present=False,
                mrz_valid=None,
                field_sources=field_sources,
                field_source_kinds=field_source_kinds,
                visual_values=dict(visual),
            ),
            None,
        )

    # Prefer MRZ fields when MRZ is valid; otherwise, use MRZ conservatively.
    use_mrz = bool(mrz.valid)
    chosen = {
        name: _choose_field(
            visual[name],
            visual_indices[name],
            getattr(mrz, name),
            mrz_indices,
            use_mrz=use_mrz,
            origins=origins,
        )
        for name in visual
    }
    full_name, dob, gender, nationality, doc_num = (chosen[name][0] for name in (
        "full_name",
        "date_of_birth",
        "gender",
        "nationality",
        "document_number",
    ))

    source = "mrz" if use_mrz else "mrz+visual"
    if not use_mrz and any(visual.values()):
        source = "mrz+visual"

    return (
        IdentityExtraction(
            full_name=full_name,
            date_of_birth=dob,
            gender=gender,
            nationality=nationality,
            document_number=doc_num,
            document_type=mrz.document_type or "unknown",
            extraction_source=source,
            mrz_present=True,
            mrz_valid=mrz.valid,
            field_sources={name: chosen[name][1] for name in visual},
            field_source_kinds={name: chosen[name][2] for name in visual},
            visual_values=dict(visual),
        ),
        mrz,
    )

