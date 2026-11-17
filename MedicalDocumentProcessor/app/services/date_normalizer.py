"""Date normalization applied to the extracted text before any AI step sees it.

Documents print numeric dates as ``16/11/2026`` (day first) or ``11/16/2026`` (month
first). The model has to guess which one, and a wrong guess can swap a recent document
into the past. This module rewrites every numeric date in the text to ISO
(``YYYY-MM-DD``) first, so the rest of the pipeline reads one unambiguous format.

How the day/month order of a document is decided:

1. From the numbers. A value above 12 can only be a day (``16/11/2026`` is day first,
   ``11/16/2026`` is month first). Every date in the document that carries such a value
   votes for its order.
2. If no date settles it (every date reads ``02/03/2026``), the patient's birth date
   settles it. A slash date in the document that equals the birth date under exactly one
   order reveals the order (birth date 2004-03-02: ``02/03/2004`` is day first and
   ``03/02/2004`` is month first).
3. If both steps stay silent, the default order is used (day first).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

DAY_FIRST = "dmy"
MONTH_FIRST = "mdy"
DEFAULT_ORDER = DAY_FIRST

# 1-2 digit day/month, the same separator twice, a 4-digit year. The look-arounds keep it
# away from reference ranges ("10.0 - 40.0"), phone numbers and ISO dates.
_NUMERIC_DATE = re.compile(r"(?<![\d./\-])(\d{1,2})([/.\-])(\d{1,2})\2(\d{4})(?!\d)")
_ISO_DATE = re.compile(r"(?<![\d\-])(\d{4})-(\d{2})-(\d{2})(?![\d\-])")
_BIRTH_LINE = re.compile(r"birth|d\.?\s?o\.?\s?b\b|\bage\b", re.IGNORECASE)


@dataclass(frozen=True)
class DateNormalization:
    text: str
    order: str  # "dmy" or "mdy"
    order_source: str  # "numbers", "birth_date" or "default"
    converted: int  # how many dates were rewritten to ISO


def parse_birth_date(value: Optional[str]) -> Optional[date]:
    """Birth date from the patient record (ISO). Returns None when absent or invalid."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _build(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _orders_allowed_by_numbers(first: int, second: int) -> List[str]:
    """Orders that the two leading numbers allow. A value above 12 cannot be a month."""
    allowed = []
    if second <= 12 and 1 <= first <= 31:
        allowed.append(DAY_FIRST)
    if first <= 12 and 1 <= second <= 31:
        allowed.append(MONTH_FIRST)
    return allowed


def _interpret(first: int, second: int, year: int, order: str) -> Optional[date]:
    if order == DAY_FIRST:
        return _build(year, second, first)
    return _build(year, first, second)


def _order_from_numbers(text: str) -> Optional[str]:
    """The order that every self-deciding date in the text agrees on, if any."""
    found = set()
    for match in _NUMERIC_DATE.finditer(text):
        first, second, year = int(match.group(1)), int(match.group(3)), int(match.group(4))
        allowed = [o for o in _orders_allowed_by_numbers(first, second) if _interpret(first, second, year, o)]
        if len(allowed) == 1:
            found.add(allowed[0])
    if len(found) == 1:
        return next(iter(found))
    return None


def _order_from_birth_date(text: str, birth_date: Optional[date]) -> Optional[str]:
    """The order under which a date in the text equals the birth date, if only one does."""
    if birth_date is None:
        return None
    votes = set()
    for match in _NUMERIC_DATE.finditer(text):
        first, second, year = int(match.group(1)), int(match.group(3)), int(match.group(4))
        matching = [o for o in (DAY_FIRST, MONTH_FIRST) if _interpret(first, second, year, o) == birth_date]
        if len(matching) == 1:
            votes.add(matching[0])
    if len(votes) == 1:
        return next(iter(votes))
    return None


def infer_date_order(text: str, birth_date: Optional[date] = None) -> Tuple[str, str]:
    """Return ``(order, source)`` for the numeric dates in ``text``."""
    order = _order_from_numbers(text)
    if order:
        return order, "numbers"
    order = _order_from_birth_date(text, birth_date)
    if order:
        return order, "birth_date"
    return DEFAULT_ORDER, "default"


def normalize_dates(text: str, birth_date: Optional[date] = None) -> DateNormalization:
    """Rewrite every numeric date in ``text`` to ISO (YYYY-MM-DD).

    A date whose own numbers decide the order keeps that order. A date that reads the same
    both ways follows the order of the document. Impossible dates (31/02/2026) stay as
    printed.
    """
    text = text or ""
    doc_order, source = infer_date_order(text, birth_date)
    converted = 0

    def replace(match: "re.Match[str]") -> str:
        nonlocal converted
        first, second, year = int(match.group(1)), int(match.group(3)), int(match.group(4))
        allowed = [o for o in _orders_allowed_by_numbers(first, second) if _interpret(first, second, year, o)]
        if not allowed:
            return match.group(0)
        order = allowed[0] if len(allowed) == 1 else (doc_order if doc_order in allowed else allowed[0])
        parsed = _interpret(first, second, year, order)
        if parsed is None:
            return match.group(0)
        converted += 1
        return parsed.isoformat()

    return DateNormalization(
        text=_NUMERIC_DATE.sub(replace, text),
        order=doc_order,
        order_source=source,
        converted=converted,
    )


def find_document_date(text: str, birth_date: Optional[date] = None, today: Optional[date] = None) -> Optional[date]:
    """Latest clinical date printed in already-normalized text.

    Lines about birth or age and any date equal to the birth date are skipped. Dates after
    today are used only when nothing else is printed.
    """
    today = today or date.today()
    dates: List[date] = []
    for line in (text or "").splitlines():
        if _BIRTH_LINE.search(line):
            continue
        for match in _ISO_DATE.finditer(line):
            parsed = _build(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            if parsed is not None and parsed != birth_date:
                dates.append(parsed)
    if not dates:
        return None
    past = [d for d in dates if d <= today]
    return max(past) if past else max(dates)
