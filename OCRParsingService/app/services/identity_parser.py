"""Identity document field extraction from OCR text.

Strategy:
1) Prefer MRZ parsing (high precision, layout-independent) when present.
2) Fallback to label-based extraction from the visual inspection zone.
3) Optionally allow an LLM fallback (existing parsing_service) to fill gaps,
   but always validate/normalize the output.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def _extract_labeled_value(lines: list[str], label_patterns: list[re.Pattern[str]]) -> str | None:
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
                return _clean_spaces(value)
            # label-only; use next non-empty line
            for j in range(idx + 1, min(idx + 4, len(lines))):
                nxt = lines[j].strip()
                if nxt:
                    return _clean_spaces(nxt)
    return None


def _extract_gender(lines: list[str]) -> str | None:
    patterns = [
        re.compile(r"(?i)\b(?:sex|gender)\b\s*[:\-]?\s*(?P<value>M|F|MALE|FEMALE|X|UNSPECIFIED)\b"),
    ]
    v = _extract_labeled_value(lines, patterns)
    if not v:
        return None
    v = v.upper()
    if v in ("M", "MALE"):
        return "male"
    if v in ("F", "FEMALE"):
        return "female"
    if v in ("X", "UNSPECIFIED"):
        return "unspecified"
    return None


def _extract_document_number(lines: list[str]) -> str | None:
    patterns = [
        re.compile(r"(?i)\b(?:passport|document|doc|id|card)\s*(?:no|number|#)\b\s*[:\-]?\s*(?P<value>[A-Z0-9<]{5,20})"),
        re.compile(r"(?i)\b(?:passport)\b\s*[:\-]?\s*(?P<value>[A-Z0-9<]{5,20})"),
    ]
    v = _extract_labeled_value(lines, patterns)
    if not v:
        return None
    v = v.replace("<", "").strip()
    v = re.sub(r"[^A-Z0-9]", "", v.upper())
    return v or None


def _extract_nationality(lines: list[str]) -> str | None:
    patterns = [
        re.compile(r"(?i)\bnationality\b\s*[:\-]?\s*(?P<value>[A-Z][A-Z \-]{2,})"),
        re.compile(r"(?i)\bnation(?:ality)?\b\s*[:\-]?\s*(?P<value>[A-Z][A-Z \-]{2,})"),
    ]
    v = _extract_labeled_value(lines, patterns)
    if not v:
        return None
    return re.sub(r"[^A-Z \-]", "", v.upper()).strip() or None


def _extract_dob(lines: list[str]) -> str | None:
    patterns = [
        re.compile(r"(?i)\b(?:date\s*of\s*birth|birth\s*date|dob)\b\s*[:\-]?\s*(?P<value>.+)$"),
    ]
    v = _extract_labeled_value(lines, patterns)
    if not v:
        return None
    return _parse_visual_date(v)


def _extract_full_name(lines: list[str]) -> str | None:
    patterns = [
        re.compile(r"(?i)\bfull\s*name\b\s*[:\-]?\s*(?P<value>.+)$"),
        re.compile(r"(?i)\bname\b\s*[:\-]?\s*(?P<value>.+)$"),
    ]
    v = _extract_labeled_value(lines, patterns)
    if v:
        # Avoid returning "NAME" extracted from decorative lines.
        if len(v) >= 2:
            return v

    # Try combining "Surname/Family Name" + "Given Names"
    surname = _extract_labeled_value(
        lines,
        [
            re.compile(r"(?i)\b(?:surname|family\s*name|last\s*name)\b\s*[:\-]?\s*(?P<value>.+)$"),
        ],
    )
    given = _extract_labeled_value(
        lines,
        [
            re.compile(r"(?i)\b(?:given\s*names?|first\s*name)\b\s*[:\-]?\s*(?P<value>.+)$"),
        ],
    )
    combined = " ".join(p for p in [surname, given] if p)
    return combined or None


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


def extract_identity(text_lines: list[str]) -> tuple[IdentityExtraction, MRZParseResult | None]:
    clean_lines = [_clean_spaces(line) for line in text_lines if line and line.strip()]
    mrz = parse_mrz(clean_lines)

    visual = {
        "full_name": _extract_full_name(clean_lines),
        "date_of_birth": _extract_dob(clean_lines),
        "gender": _extract_gender(clean_lines),
        "nationality": _extract_nationality(clean_lines),
        "document_number": _extract_document_number(clean_lines),
    }

    if mrz is None:
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
            ),
            None,
        )

    # Prefer MRZ fields when MRZ is valid; otherwise, use MRZ conservatively.
    use_mrz = bool(mrz.valid)
    full_name = mrz.full_name if (use_mrz and mrz.full_name) else (visual["full_name"] or mrz.full_name)
    dob = mrz.date_of_birth if (use_mrz and mrz.date_of_birth) else (visual["date_of_birth"] or mrz.date_of_birth)
    gender = mrz.gender if (use_mrz and mrz.gender) else (visual["gender"] or mrz.gender)
    nationality = mrz.nationality if (use_mrz and mrz.nationality) else (visual["nationality"] or mrz.nationality)
    doc_num = mrz.document_number if (use_mrz and mrz.document_number) else (visual["document_number"] or mrz.document_number)

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
        ),
        mrz,
    )

