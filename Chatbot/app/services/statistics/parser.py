"""Request parsing for statistics/analytics queries (deterministic)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class TimeRange:
    type: str
    start_date: date
    end_date_exclusive: date

    def to_filter_label(self) -> str:
        return self.type


def _add_months(d: date, months: int) -> date:
    """Add months to a date, snapping to the first of month (we only use month starts)."""
    y = d.year
    m = d.month + months
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return date(y, m, 1)


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _week_start_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


_LAST_N_MONTHS_RE = re.compile(r"\blast\s+(\d{1,4})\s+months?\b", re.IGNORECASE)
_LAST_N_UNITS_RE = re.compile(r"\blast\s+(\d{1,5})\s+(day|days|week|weeks|month|months|year|years)\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})\b")
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_BETWEEN_RE = re.compile(r"\b(?:between|from)\s+(.+?)\s+(?:and|to)\s+(.+?)\b", re.IGNORECASE)
_SINCE_RE = re.compile(r"\bsince\s+(.+?)\b", re.IGNORECASE)
_ALL_TIME_RE = re.compile(
    r"\b(all\s*time|all-time|overall|entire\s+period|ever|since\s+the\s+beginning|lifetime)\b",
    re.IGNORECASE,
)

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_MONTH_YEAR_RE = re.compile(
    r"\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t)?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")\s+(19\d{2}|20\d{2}|21\d{2})\b",
    re.IGNORECASE,
)


def _all_time_range(*, reference_date: date) -> TimeRange:
    # A "practically unbounded" range. We keep an end bound for deterministic
    # semantics and to avoid depending on DB MAX(date) queries.
    tomorrow = reference_date + timedelta(days=1)
    return TimeRange(type="all_time", start_date=date(1900, 1, 1), end_date_exclusive=tomorrow)


def _parse_month_year(s: str) -> Optional[Tuple[date, date]]:
    m = _MONTH_YEAR_RE.search(s or "")
    if not m:
        return None
    month_token = m.group(1).lower()
    year = int(m.group(2))
    month = _MONTHS.get(month_token[:3], _MONTHS.get(month_token))
    if not month:
        return None
    start = date(year, month, 1)
    end = _add_months(start, 1)
    return start, end


def _parse_year_only(s: str) -> Optional[Tuple[date, date]]:
    m = _YEAR_RE.search(s or "")
    if not m:
        return None
    year = int(m.group(1))
    start = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    return start, end


def _parse_iso_date_only(s: str) -> Optional[Tuple[date, date]]:
    m = _ISO_DATE_RE.search(s or "")
    if not m:
        return None
    d = date.fromisoformat(m.group(1))
    return d, d + timedelta(days=1)


def _parse_range_endpoint(s: str) -> Optional[Tuple[date, date]]:
    # Returns an endpoint range (start, end_exclusive) for a single token like:
    # - 2026-04-22
    # - March 2026
    # - 2026
    return _parse_iso_date_only(s) or _parse_month_year(s) or _parse_year_only(s)


def parse_time_range(text: str, *, reference_date: Optional[date] = None) -> TimeRange:
    tl = (text or "").strip().lower()
    if not tl:
        raise ValueError("time_range is required")

    ref = reference_date or date.today()
    tomorrow = ref + timedelta(days=1)

    if _ALL_TIME_RE.search(tl):
        return _all_time_range(reference_date=ref)

    if re.search(r"\btoday\b", tl):
        return TimeRange(type="today", start_date=ref, end_date_exclusive=tomorrow)

    if re.search(r"\btomorrow\b", tl):
        start = tomorrow
        return TimeRange(type="tomorrow", start_date=start, end_date_exclusive=start + timedelta(days=1))

    if re.search(r"\bthis\s+week\b", tl):
        start = _week_start_monday(ref)
        return TimeRange(type="this_week", start_date=start, end_date_exclusive=tomorrow)

    if re.search(r"\blast\s+week\b", tl):
        this_start = _week_start_monday(ref)
        start = this_start - timedelta(days=7)
        return TimeRange(type="last_week", start_date=start, end_date_exclusive=this_start)

    if re.search(r"\bnext\s+week\b", tl):
        this_start = _week_start_monday(ref)
        start = this_start + timedelta(days=7)
        end = start + timedelta(days=7)
        return TimeRange(type="next_week", start_date=start, end_date_exclusive=end)

    if re.search(r"\bthis\s+month\b", tl):
        start = _month_start(ref)
        return TimeRange(type="this_month", start_date=start, end_date_exclusive=tomorrow)

    if re.search(r"\blast\s+month\b", tl):
        this_start = _month_start(ref)
        start = _add_months(this_start, -1)
        return TimeRange(type="last_month", start_date=start, end_date_exclusive=this_start)

    if re.search(r"\bnext\s+month\b", tl):
        this_start = _month_start(ref)
        start = _add_months(this_start, 1)
        end = _add_months(this_start, 2)
        return TimeRange(type="next_month", start_date=start, end_date_exclusive=end)

    m = _LAST_N_MONTHS_RE.search(tl)
    if m:
        n = int(m.group(1))
        if n <= 0:
            return _all_time_range(reference_date=ref)
        this_start = _month_start(ref)
        try:
            start = _add_months(this_start, -(n - 1))
        except Exception:
            return _all_time_range(reference_date=ref)
        return TimeRange(type=f"last_{n}_months", start_date=start, end_date_exclusive=tomorrow)

    if re.search(r"\bthis\s+year\b", tl):
        start = date(ref.year, 1, 1)
        return TimeRange(type="this_year", start_date=start, end_date_exclusive=tomorrow)

    if re.search(r"\blast\s+year\b", tl):
        start = date(ref.year - 1, 1, 1)
        end = date(ref.year, 1, 1)
        return TimeRange(type="last_year", start_date=start, end_date_exclusive=end)

    if re.search(r"\bnext\s+year\b", tl):
        start = date(ref.year + 1, 1, 1)
        end = date(ref.year + 2, 1, 1)
        return TimeRange(type="next_year", start_date=start, end_date_exclusive=end)

    m = _LAST_N_UNITS_RE.search(tl)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if n <= 0:
            return _all_time_range(reference_date=ref)
        if unit.startswith("day"):
            start = ref - timedelta(days=(n - 1))
            return TimeRange(type=f"last_{n}_days", start_date=start, end_date_exclusive=tomorrow)
        if unit.startswith("week"):
            start = ref - timedelta(days=(7 * n - 1))
            return TimeRange(type=f"last_{n}_weeks", start_date=start, end_date_exclusive=tomorrow)
        if unit.startswith("month"):
            this_start = _month_start(ref)
            try:
                start = _add_months(this_start, -(n - 1))
            except Exception:
                return _all_time_range(reference_date=ref)
            return TimeRange(type=f"last_{n}_months", start_date=start, end_date_exclusive=tomorrow)
        if unit.startswith("year"):
            start_year = ref.year - (n - 1)
            if start_year < 1:
                return _all_time_range(reference_date=ref)
            start = date(start_year, 1, 1)
            return TimeRange(type=f"last_{n}_years", start_date=start, end_date_exclusive=tomorrow)

    m = _BETWEEN_RE.search(tl)
    if m:
        left = (m.group(1) or "").strip()
        right = (m.group(2) or "").strip()
        left_range = _parse_range_endpoint(left)
        right_range = _parse_range_endpoint(right)
        if left_range and right_range:
            start = left_range[0]
            end = right_range[1]
            if end <= start:
                raise ValueError("Invalid time range (end <= start)")
            return TimeRange(type="custom_range", start_date=start, end_date_exclusive=end)

    m = _SINCE_RE.search(tl)
    if m:
        token = (m.group(1) or "").strip()
        endpoint = _parse_range_endpoint(token)
        if endpoint:
            return TimeRange(type="since", start_date=endpoint[0], end_date_exclusive=tomorrow)

    # Handle "in <month year>" / "in <year>".
    if re.search(r"\bin\b", tl):
        my = _parse_month_year(tl)
        if my:
            return TimeRange(type="in_month", start_date=my[0], end_date_exclusive=my[1])
        y = _parse_year_only(tl)
        if y:
            return TimeRange(type=f"year_{y[0].year}", start_date=y[0], end_date_exclusive=y[1])

    # Default: no explicit/recognized time range -> all-time.
    return _all_time_range(reference_date=ref)


def _parse_top_n(text: str) -> Optional[int]:
    tl = (text or "").lower()
    m = re.search(r"\btop\s+(\d{1,3})\b", tl)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 100 else None
    if "top" in tl or "busiest" in tl or "most common" in tl:
        return 5
    return None


def _parse_metric(text: str) -> str:
    tl = (text or "").lower()
    if re.search(r"\b(avg|average)\b", tl):
        return "avg"
    if re.search(r"\b(sum|total)\b", tl):
        return "sum"
    return "count"


def _parse_entity(text: str) -> str:
    tl = (text or "").lower()
    if re.search(r"\b(admission|admissions|admitted)\b", tl):
        return "admissions"
    if re.search(r"\b(department|departments|unit|units|ward|wards)\b", tl):
        return "departments"
    if re.search(r"\b(diagnosis|diagnoses|dx)\b", tl):
        return "diagnosis"
    # Default to diagnosis for ambiguous "top diagnoses"/"trend" queries.
    return "diagnosis"


def _parse_intent_and_grouping(text: str, *, entity: str) -> Tuple[str, Optional[str]]:
    tl = (text or "").lower()

    if re.search(r"\b(trend|trends)\b", tl) or re.search(r"\bover\s+the\s+last\b", tl):
        return f"{entity}_trend", "month"

    if re.search(r"\b(distribution|breakdown)\b", tl):
        if entity == "diagnosis":
            return "diagnosis_distribution", entity
        if entity == "departments":
            return "department_distribution", "department"
        return f"{entity}_distribution", entity

    if re.search(r"\b(top|most common|busiest)\b", tl):
        if entity == "diagnosis":
            return "top_diagnoses", "diagnosis"
        if entity == "departments":
            return "busiest_departments", "department"
        return f"top_{entity}", entity

    if entity == "admissions" and re.search(r"\bhow\s+many\b", tl):
        return "admissions_count", None

    return f"{entity}_count", None


def parse_statistics_request(text: str, *, reference_date: Optional[date] = None) -> Dict[str, Any]:
    """
    Parse a statistics query into a structured, deterministic request.

    Returns a dict with required fields:
    - metric
    - entity
    - group_by (optional)
    - top_n (optional)
    - time_range (optional in input; defaults to all_time)
    """
    if not (text or "").strip():
        raise ValueError("Empty query")

    time_range = parse_time_range(text, reference_date=reference_date)
    entity = _parse_entity(text)
    metric = _parse_metric(text)
    top_n = _parse_top_n(text)
    intent, group_by = _parse_intent_and_grouping(text, entity=entity)

    parsed: Dict[str, Any] = {
        "intent": intent,
        "metric": metric,
        "entity": entity,
        "group_by": group_by,
        "top_n": top_n,
        "time_range": {
            "type": time_range.type,
            "start_date": time_range.start_date.isoformat(),
            "end_date_exclusive": time_range.end_date_exclusive.isoformat(),
        },
    }

    if parsed["metric"] != "count" and entity in ("diagnosis", "admissions", "departments"):
        # For now, keep metric parsed but the SQL builder may restrict supported metrics per entity.
        pass

    return parsed
