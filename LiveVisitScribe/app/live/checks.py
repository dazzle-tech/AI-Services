"""Evidence checks for the picked-up list. A check that is unsure drops the item or the detail."""

from __future__ import annotations

import re

_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_DIGIT_RE = re.compile(r"\d+(?:[.,]\d+)?")
_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Longer phrases first so "twenty" is not read as "two".
_SPELLED = (
    ("zero", "0"),
    ("one", "1"),
    ("two", "2"),
    ("three", "3"),
    ("four", "4"),
    ("five", "5"),
    ("six", "6"),
    ("seven", "7"),
    ("eight", "8"),
    ("nine", "9"),
    ("ten", "10"),
    ("eleven", "11"),
    ("twelve", "12"),
    ("thirteen", "13"),
    ("fourteen", "14"),
    ("fifteen", "15"),
    ("sixteen", "16"),
    ("seventeen", "17"),
    ("eighteen", "18"),
    ("nineteen", "19"),
    ("twenty", "20"),
)
_SPELLED_RE = re.compile(r"\b(?:" + "|".join(word for word, _number in _SPELLED) + r")\b", re.IGNORECASE)
_SPELLED_VALUE = {word: number for word, number in _SPELLED}

# Order matters: mcg before mg, and mg before a bare g.
_UNITS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mcg", re.compile(r"\b(?:mcg|micrograms?|µg|μg|ug)\b|ميكروغرام", re.IGNORECASE)),
    ("mg", re.compile(r"\b(?:mg|milligrams?)\b|ملغم|ملغ", re.IGNORECASE)),
    ("g", re.compile(r"\b(?:g|grams?)\b|غرام", re.IGNORECASE)),
    ("ml", re.compile(r"\b(?:ml|millilit(?:re|er)s?)\b|(?<![\w])مل(?!غ)", re.IGNORECASE)),
    ("iu", re.compile(r"\b(?:iu|units?)\b|وحدة", re.IGNORECASE)),
    ("form", re.compile(r"\b(?:tablets?|pills?|capsules?)\b|كبسولات|كبسولة|أقراص|قرص|حبات|حبة", re.IGNORECASE)),
    ("puff", re.compile(r"\bpuffs?\b|بخات|بخة", re.IGNORECASE)),
    ("drop", re.compile(r"\bdrops?\b|قطرات|قطرة", re.IGNORECASE)),
)

_FREQUENCIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("twice", re.compile(r"\btwice\b|مرتين", re.IGNORECASE)),
    ("thrice", re.compile(r"\bthrice\b|\bthree times\b|\b3 times\b|ثلاث مرات", re.IGNORECASE)),
    ("four", re.compile(r"\bfour times\b|\b4 times\b|أربع مرات|اربعة مرات|أربعة مرات", re.IGNORECASE)),
    ("once", re.compile(r"\bonce\b|مرة واحدة|(?<![\w])مرة(?!ين)", re.IGNORECASE)),
    ("hourly", re.compile(r"\bhourly\b|\bevery\s+\d+\s+hours?\b|كل ساعة", re.IGNORECASE)),
    ("daily", re.compile(r"\bdaily\b|\ba day\b|\bper day\b|\bevery day\b|يومياً|يوميا", re.IGNORECASE)),
    ("weekly", re.compile(r"\bweekly\b|\ba week\b|\bper week\b|\bevery week\b|أسبوعيا", re.IGNORECASE)),
    ("night", re.compile(r"\b(?:at night|nightly|every night)\b|ليلاً|ليلا", re.IGNORECASE)),
    ("morning", re.compile(r"\bmorning\b|صباحًا|صباحا", re.IGNORECASE)),
    ("evening", re.compile(r"\bevening\b|مساءً|مساء", re.IGNORECASE)),
    ("prn", re.compile(r"\bprn\b|\bas needed\b|عند الحاجة", re.IGNORECASE)),
)

_CLAUSE_SPLIT = re.compile(
    r"\s*(?:[,;.!?؟،:]|\b(?:but|however)\b|لكن|بس)\s*",
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(
    r"\b(?:no|not|none|never|without|denies|denied|deny|nothing|negative|nil|neither|nor|cannot)\b"
    r"|n't\b",
    re.IGNORECASE,
)
_ARABIC_PHRASES = ("ماعندي", "مافيه", "مافي", "بدون", "ليست", "ليس", "بلا")
_ARABIC_TOKENS = ("لا", "ما", "مو", "مش", "لم", "لن")
_STOP = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "for", "with", "my", "is", "it", "have",
    "had", "has", "was", "were", "been", "be", "from", "that", "this", "any", "i", "you", "your",
    "me", "we", "do", "did", "am", "are", "but", "however", "about", "just", "not", "no", "yes",
    "there", "here", "at", "as", "if", "when", "what", "who",
    "في", "من", "على", "عن", "ما", "لا", "أنا", "اني",
}


def _western_digits(text: str) -> str:
    chars: list[str] = []
    for char in text:
        code = ord(char)
        if 0x0660 <= code <= 0x0669:
            chars.append(chr(code - 0x0660 + 48))
        elif 0x06F0 <= code <= 0x06F9:
            chars.append(chr(code - 0x06F0 + 48))
        else:
            chars.append(char)
    return "".join(chars)


def numbers_of(text: str) -> set[str]:
    """Western digits, Arabic-Indic and Persian digits, and English zero..twenty."""
    western = _western_digits(text)
    found = {match.group(0).replace(",", ".") for match in _DIGIT_RE.finditer(western)}
    for match in _SPELLED_RE.finditer(western):
        found.add(_SPELLED_VALUE[match.group(0).lower()])
    return found


def _classes(text: str, table: tuple[tuple[str, re.Pattern[str]], ...]) -> set[str]:
    return {name for name, pattern in table if pattern.search(text)}


def dose_is_supported(detail: str, spoken: str) -> bool:
    """True when every number, unit class and frequency class in the detail was said."""
    if numbers_of(detail) - numbers_of(spoken):
        return False
    if _classes(detail, _UNITS) - _classes(spoken, _UNITS):
        return False
    if _classes(detail, _FREQUENCIES) - _classes(spoken, _FREQUENCIES):
        return False
    return True


def mentions(spoken: str, name: str) -> bool:
    """Whole word for a Latin name. An Arabic name may match inside a prefixed form (ال / بال)."""
    name = name.strip()
    if not name:
        return False
    if _ARABIC_RE.search(name):
        return name in spoken
    return re.search(rf"\b{re.escape(name)}\b", spoken, re.IGNORECASE) is not None


def has_negation(text: str) -> bool:
    if _NEGATION_RE.search(text):
        return True
    compact = re.sub(r"\s+", "", text)
    if any(phrase in compact for phrase in _ARABIC_PHRASES):
        return True
    tokens = set(_WORD_RE.findall(text))
    return any(token in tokens for token in _ARABIC_TOKENS)


def _content_words(text: str) -> set[str]:
    words: set[str] = set()
    for token in _WORD_RE.findall(text):
        word = token.lower()
        if len(word) >= 3 and word not in _STOP:
            words.add(word)
    return words


def _clauses(text: str) -> list[str]:
    return [part.strip() for part in _CLAUSE_SPLIT.split(text) if part.strip()]


def polarity_ok(item_text: str, cited_texts: list[str]) -> bool:
    """False when the cited words deny the item. An item that already says the denial ("No aura") stays."""
    if has_negation(item_text):
        return True
    item_words = _content_words(item_text)
    chosen: list[str] = []
    for line in cited_texts:
        clauses = _clauses(line) or [line.strip()]
        shared = [clause for clause in clauses if item_words & _content_words(clause)]
        if shared:
            chosen.extend(shared)
        elif len(_WORD_RE.findall(line)) <= 6:
            chosen.extend(clauses)
    return not any(has_negation(clause) for clause in chosen)
