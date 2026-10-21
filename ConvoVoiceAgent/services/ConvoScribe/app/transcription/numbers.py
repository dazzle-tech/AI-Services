"""Write spoken numbers as digits in transcript text.

"two" becomes "2", "thirty six point eight" becomes "36.8", "one twenty two" becomes "122".
Words that are not a number stay as words ("one of", "no one", "twice").
"""

from __future__ import annotations

import re

_ONES: dict[str, int] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS: dict[str, int] = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
# Arabic cardinals, including the "and" form (وعشرين) and common spellings.
_ARABIC: dict[str, str] = {
    "صفر": "zero",
    "واحد": "one",
    "واحدة": "one",
    "اثنين": "two",
    "اثنان": "two",
    "اتنين": "two",
    "ثلاثة": "three",
    "ثلاث": "three",
    "اربعة": "four",
    "أربعة": "four",
    "اربع": "four",
    "أربع": "four",
    "خمسة": "five",
    "خمس": "five",
    "ستة": "six",
    "ست": "six",
    "سبعة": "seven",
    "سبع": "seven",
    "ثمانية": "eight",
    "ثمان": "eight",
    "تسعة": "nine",
    "تسع": "nine",
    "عشرة": "ten",
    "عشر": "ten",
    "عشرين": "twenty",
    "ثلاثين": "thirty",
    "اربعين": "forty",
    "أربعين": "forty",
    "خمسين": "fifty",
    "ستين": "sixty",
    "سبعين": "seventy",
    "ثمانين": "eighty",
    "تسعين": "ninety",
    "مية": "hundred",
    "مئة": "hundred",
    "مائة": "hundred",
    "الف": "thousand",
    "ألف": "thousand",
    "فاصلة": "point",
    "نقطة": "point",
}

_TOKEN_RE = re.compile(r"\s+|\w+(?:-\w+)*|[^\w\s]", re.UNICODE)
_SINGLE_DIGIT = {name for name, value in _ONES.items() if value < 10} | {"oh"}
_NUMBER_WORDS = set(_ONES) | set(_TENS) | {"hundred", "thousand", "point", "decimal", "and", "a", "half", "oh"}


def spoken_numbers_to_digits(text: str) -> str:
    parts = _TOKEN_RE.findall(text)
    if not parts:
        return text
    out: list[str] = []
    index = 0
    while index < len(parts):
        consumed, replacement = _match(parts, index)
        if consumed:
            out.append(replacement)
            index += consumed
        else:
            out.append(parts[index])
            index += 1
    return "".join(out)


def _match(parts: list[str], start: int) -> tuple[int, str]:
    words: list[str] = []
    last_word_index = start
    best = (0, "")
    index = start
    while index < len(parts):
        if parts[index].isspace():
            if not words:
                return 0, ""
            index += 1
            continue
        canon = _canon(parts[index])
        if canon is None:
            break
        words.extend(canon)
        last_word_index = index
        rendered = _render(words)
        if rendered is not None and _allowed(parts, start, words):
            best = (last_word_index - start + 1, rendered)
        index += 1
    return best


def _canon(token: str) -> list[str] | None:
    raw = token.lower()
    if raw in {"a", "and", "half"}:
        return [raw]
    arabic = raw[1:] if raw.startswith("و") and len(raw) > 1 and raw[1:] in _ARABIC else raw
    if arabic in _ARABIC:
        word = _ARABIC[arabic]
        if raw.startswith("و") and arabic != raw:
            return ["and", word]
        return [word]
    pieces = raw.split("-")
    if pieces and all(piece in _NUMBER_WORDS and piece not in {"a", "and", "half"} for piece in pieces):
        return pieces
    return None


def _allowed(parts: list[str], start: int, words: list[str]) -> bool:
    if words != ["one"]:
        return True
    previous = ""
    for part in reversed(parts[:start]):
        if not part.isspace():
            previous = part.lower()
            break
    if previous == "no":
        return False
    return _word_after(parts, start) != "of"


def _word_after(parts: list[str], start: int) -> str:
    """First word after this token that is not itself a number word."""
    passed_start = False
    for part in parts[start:]:
        if part.isspace():
            continue
        if not passed_start:
            passed_start = True
            continue
        if _canon(part) is not None:
            continue
        return part.lower()
    return ""


def _render(words: list[str]) -> str | None:
    body = list(words)
    half = False
    if len(body) >= 3 and body[-3:] == ["and", "a", "half"]:
        half = True
        body = body[:-3]
    if not body or body[-1] in {"and", "point", "decimal", "a"}:
        return None
    if all(word in _SINGLE_DIGIT for word in body):
        if body == ["oh"]:
            return None
        digits = "".join("0" if word in {"zero", "oh"} else str(_ONES[word]) for word in body)
        return f"{digits}.5" if half else digits
    value = _parse_compound(body)
    if value is None:
        return None
    if half and "." in value:
        return None
    return f"{value}.5" if half else value


def _parse_compound(words: list[str]) -> str | None:
    total = 0
    current = 0
    seen = False
    shorthand = False
    for index, word in enumerate(words):
        if word == "and":
            if not seen:
                return None
            continue
        if word in {"point", "decimal"}:
            if not seen:
                return None
            fraction = _fraction(words[index + 1 :])
            if fraction is None:
                return None
            return f"{total + current}.{fraction}"
        if word == "hundred":
            current = (current or 1) * 100
            shorthand = False
            seen = True
            continue
        if word == "thousand":
            total += (current or 1) * 1000
            current = 0
            shorthand = False
            seen = True
            continue
        if word in _TENS:
            # "one twenty two" is 122. "two and twenty" (Arabic اثنين وعشرين) is 22.
            joined = index > 0 and words[index - 1] == "and"
            if (
                not shorthand
                and not joined
                and current in range(1, 10)
                and "hundred" not in words
                and "thousand" not in words
            ):
                current = current * 100 + _TENS[word]
                shorthand = True
            elif shorthand:
                return None
            else:
                current += _TENS[word]
            seen = True
            continue
        if word in _ONES or word == "oh":
            if word == "oh" and not seen:
                return None
            current += 0 if word == "oh" else _ONES[word]
            seen = True
            continue
        if word == "a" and not seen and index + 1 < len(words) and words[index + 1] in {"hundred", "thousand"}:
            current = 1
            seen = True
            continue
        return None
    if not seen:
        return None
    return str(total + current)


def _fraction(words: list[str]) -> str | None:
    if not words or any(word not in _SINGLE_DIGIT for word in words):
        return None
    return "".join("0" if word in {"zero", "oh"} else str(_ONES[word]) for word in words)
