"""MRZ parsing utilities (ICAO 9303) for passports and ID cards.

This parser is intentionally conservative:
- It only uses MRZ when it can find plausible MRZ lines.
- It validates check digits when possible and exposes validity in the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re


_MRZ_REPLACEMENTS: dict[str, str] = {
    "«": "<",
    "‹": "<",
    "˂": "<",
    "＜": "<",
}


def _normalize_mrz_line(line: str) -> str:
    normalized = line.strip().upper()
    for src, dst in _MRZ_REPLACEMENTS.items():
        normalized = normalized.replace(src, dst)
    # Remove spaces and keep only MRZ alphabet.
    normalized = normalized.replace(" ", "")
    normalized = re.sub(r"[^A-Z0-9<]", "", normalized)
    return normalized


def _char_value(ch: str) -> int:
    if "0" <= ch <= "9":
        return ord(ch) - ord("0")
    if "A" <= ch <= "Z":
        return ord(ch) - ord("A") + 10
    # '<' and unknown map to 0
    return 0


def _check_digit(data: str) -> str:
    weights = (7, 3, 1)
    total = 0
    for i, ch in enumerate(data):
        total += _char_value(ch) * weights[i % 3]
    return str(total % 10)


def _mrz_name_to_full(name_field: str) -> str | None:
    # "SURNAME<<GIVEN<NAMES" -> "SURNAME GIVEN NAMES"
    if not name_field:
        return None
    cleaned = name_field.strip("<")
    if not cleaned:
        return None
    parts = cleaned.split("<<", 1)
    surname = parts[0].replace("<", " ").strip()
    given = ""
    if len(parts) > 1:
        given = parts[1].replace("<", " ").strip()
    full = " ".join(p for p in [surname, given] if p)
    return re.sub(r"\s+", " ", full) or None


def _sex_to_gender(sex: str) -> str | None:
    if not sex:
        return None
    sex = sex.upper()
    if sex == "M":
        return "male"
    if sex == "F":
        return "female"
    if sex == "<":
        return "unspecified"
    return None


def _parse_mrz_date(yymmdd: str, *, kind: str, today: date) -> str | None:
    """Convert YYMMDD into ISO YYYY-MM-DD using conservative century rules."""
    if not re.fullmatch(r"\d{6}", yymmdd or ""):
        return None

    yy = int(yymmdd[0:2])
    mm = int(yymmdd[2:4])
    dd = int(yymmdd[4:6])
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return None

    def safe_date(year: int) -> date | None:
        try:
            return date(year, mm, dd)
        except ValueError:
            return None

    # Candidate centuries.
    candidate_1900 = safe_date(1900 + yy)
    candidate_2000 = safe_date(2000 + yy)
    candidates = [d for d in [candidate_1900, candidate_2000] if d is not None]
    if not candidates:
        return None

    if kind == "birth":
        # Choose a date that yields a realistic age.
        best: date | None = None
        best_age_delta: int | None = None
        for cand in candidates:
            age = today.year - cand.year - ((today.month, today.day) < (cand.month, cand.day))
            if 0 <= age <= 120:
                delta = abs(age - 40)  # bias toward typical adult but keep within range
                if best is None or delta < (best_age_delta or 10**9):
                    best = cand
                    best_age_delta = delta
        if best is None:
            # If both are out of range, pick the older one (less likely future birth).
            best = min(candidates)
        return best.isoformat()

    # kind == "expiry"
    # Choose date that is closest to today but not too far in the past.
    best = None
    best_abs_days = None
    for cand in candidates:
        delta_days = abs((cand - today).days)
        if best is None or delta_days < (best_abs_days or 10**9):
            best = cand
            best_abs_days = delta_days
    return best.isoformat() if best else None


@dataclass(frozen=True)
class MRZParseResult:
    mrz_lines: list[str]
    document_type: str
    document_number: str | None
    nationality: str | None
    date_of_birth: str | None
    gender: str | None
    full_name: str | None
    valid: bool | None
    validation: dict[str, bool]


def _is_mrzish(line: str) -> bool:
    if len(line) < 25:
        return False
    if line.count("<") < 5:
        return False
    allowed = sum(ch.isalnum() or ch == "<" for ch in line)
    return allowed / max(1, len(line)) > 0.95


def find_mrz_candidates(text_lines: list[str]) -> list[str]:
    candidates: list[str] = []
    for line in text_lines:
        normalized = _normalize_mrz_line(line)
        if normalized and _is_mrzish(normalized):
            candidates.append(normalized)
    return candidates


def parse_mrz(text_lines: list[str], *, today: date | None = None) -> MRZParseResult | None:
    """Attempt to parse MRZ (TD3/TD2/TD1) from OCR lines."""
    today = today or date.today()
    candidates = find_mrz_candidates(text_lines)
    if len(candidates) < 2:
        return None

    # Prefer 2-line TD3 (passport) / TD2.
    best_two: tuple[int, str, str] | None = None
    for i in range(len(candidates) - 1):
        a, b = candidates[i], candidates[i + 1]
        if abs(len(a) - len(b)) > 2:
            continue
        score = len(a) + len(b) + (50 if a.startswith(("P<", "I<", "A<", "C<")) else 0)
        if best_two is None or score > best_two[0]:
            best_two = (score, a, b)

    if best_two is not None:
        _, line1, line2 = best_two
        two_len = max(len(line1), len(line2))
        # Try TD3 (44 chars) first, then TD2 (36 chars).
        for target_len, parser in [(44, _parse_td3), (36, _parse_td2)]:
            l1 = line1.ljust(target_len, "<")[:target_len]
            l2 = line2.ljust(target_len, "<")[:target_len]
            parsed = parser(l1, l2, today=today)
            if parsed is not None:
                return parsed

    # Try 3-line TD1 (ID card).
    for i in range(len(candidates) - 2):
        l1, l2, l3 = candidates[i], candidates[i + 1], candidates[i + 2]
        if max(abs(len(l1) - len(l2)), abs(len(l2) - len(l3))) > 2:
            continue
        target_len = 30
        p = _parse_td1(
            l1.ljust(target_len, "<")[:target_len],
            l2.ljust(target_len, "<")[:target_len],
            l3.ljust(target_len, "<")[:target_len],
            today=today,
        )
        if p is not None:
            return p

    return None


def _parse_td3(line1: str, line2: str, *, today: date) -> MRZParseResult | None:
    if len(line1) != 44 or len(line2) != 44:
        return None
    if not line1.startswith("P<"):
        # Some travel documents use other codes, but TD3 passports are most common.
        return None

    issuing = line1[2:5].replace("<", "") or None
    full_name = _mrz_name_to_full(line1[5:])

    passport_number = line2[0:9]
    passport_number_cd = line2[9]
    nationality = line2[10:13].replace("<", "") or None
    birth = line2[13:19]
    birth_cd = line2[19]
    sex = line2[20:21]
    expiry = line2[21:27]
    expiry_cd = line2[27]
    personal_number = line2[28:42]
    personal_number_cd = line2[42]
    composite_cd = line2[43]

    validation: dict[str, bool] = {}
    validation["passport_number"] = _check_digit(passport_number) == passport_number_cd
    validation["birth_date"] = _check_digit(birth) == birth_cd
    validation["expiry_date"] = _check_digit(expiry) == expiry_cd
    validation["personal_number"] = _check_digit(personal_number) == personal_number_cd
    composite_data = (
        passport_number
        + passport_number_cd
        + birth
        + birth_cd
        + expiry
        + expiry_cd
        + personal_number
        + personal_number_cd
    )
    validation["composite"] = _check_digit(composite_data) == composite_cd

    # Consider MRZ valid if the key fields validate. Composite might fail on some OCR noise.
    valid = (
        validation["passport_number"]
        and validation["birth_date"]
        and validation["expiry_date"]
    )

    document_number = passport_number.replace("<", "") or None
    date_of_birth = _parse_mrz_date(birth, kind="birth", today=today)
    gender = _sex_to_gender(sex)

    return MRZParseResult(
        mrz_lines=[line1, line2],
        document_type="passport",
        document_number=document_number,
        nationality=nationality,
        date_of_birth=date_of_birth,
        gender=gender,
        full_name=full_name,
        valid=valid,
        validation=validation | {"issuing_country": bool(issuing)},
    )


def _parse_td2(line1: str, line2: str, *, today: date) -> MRZParseResult | None:
    if len(line1) != 36 or len(line2) != 36:
        return None

    # TD2 supports various document codes. Require MRZ-like prefix.
    if not re.match(r"^[A-Z0-9]<", line1[:2]):
        return None

    full_name = _mrz_name_to_full(line1[5:])

    doc_number = line2[0:9]
    doc_number_cd = line2[9]
    nationality = line2[10:13].replace("<", "") or None
    birth = line2[13:19]
    birth_cd = line2[19]
    sex = line2[20:21]
    expiry = line2[21:27]
    expiry_cd = line2[27]
    optional = line2[28:35]
    composite_cd = line2[35]

    validation: dict[str, bool] = {}
    validation["document_number"] = _check_digit(doc_number) == doc_number_cd
    validation["birth_date"] = _check_digit(birth) == birth_cd
    validation["expiry_date"] = _check_digit(expiry) == expiry_cd
    composite_data = (
        doc_number
        + doc_number_cd
        + birth
        + birth_cd
        + expiry
        + expiry_cd
        + optional
    )
    validation["composite"] = _check_digit(composite_data) == composite_cd
    valid = validation["document_number"] and validation["birth_date"] and validation["expiry_date"]

    return MRZParseResult(
        mrz_lines=[line1, line2],
        document_type="id_card",
        document_number=doc_number.replace("<", "") or None,
        nationality=nationality,
        date_of_birth=_parse_mrz_date(birth, kind="birth", today=today),
        gender=_sex_to_gender(sex),
        full_name=full_name,
        valid=valid,
        validation=validation,
    )


def _parse_td1(line1: str, line2: str, line3: str, *, today: date) -> MRZParseResult | None:
    if len(line1) != 30 or len(line2) != 30 or len(line3) != 30:
        return None

    # TD1 line1 begins with document code (2 chars) then issuing (3).
    if not re.match(r"^[A-Z0-9]{2}[A-Z0-9<]{3}", line1[:5]):
        return None

    doc_number = line1[5:14]
    doc_number_cd = line1[14]
    optional1 = line1[15:30]

    birth = line2[0:6]
    birth_cd = line2[6]
    sex = line2[7:8]
    expiry = line2[8:14]
    expiry_cd = line2[14]
    nationality = line2[15:18].replace("<", "") or None
    optional2 = line2[18:29]
    composite_cd = line2[29]

    full_name = _mrz_name_to_full(line3)

    validation: dict[str, bool] = {}
    validation["document_number"] = _check_digit(doc_number) == doc_number_cd
    validation["birth_date"] = _check_digit(birth) == birth_cd
    validation["expiry_date"] = _check_digit(expiry) == expiry_cd
    composite_data = (
        doc_number
        + doc_number_cd
        + optional1
        + birth
        + birth_cd
        + expiry
        + expiry_cd
        + optional2
    )
    validation["composite"] = _check_digit(composite_data) == composite_cd
    valid = validation["document_number"] and validation["birth_date"] and validation["expiry_date"]

    return MRZParseResult(
        mrz_lines=[line1, line2, line3],
        document_type="id_card",
        document_number=doc_number.replace("<", "") or None,
        nationality=nationality,
        date_of_birth=_parse_mrz_date(birth, kind="birth", today=today),
        gender=_sex_to_gender(sex),
        full_name=full_name,
        valid=valid,
        validation=validation,
    )

