"""Small text helpers shared by the live segments and the picked-up checks."""

from __future__ import annotations

import re

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_UTTERANCE_RE = re.compile(r"[^.!?؟]+[.!?؟]*")
_PUNCT_RE = re.compile(r"[^\w\s]")


def detect_lang(text: str) -> str:
    """en, ar, or mixed, from the characters in the line (a drug name inside Arabic speech makes it mixed)."""
    has_arabic = bool(_ARABIC_RE.search(text))
    has_latin = bool(_LATIN_RE.search(text))
    if has_arabic and has_latin:
        return "mixed"
    return "ar" if has_arabic else "en"


def sentences(text: str) -> list[str]:
    return [part.strip() for part in _UTTERANCE_RE.findall(text) if part.strip()]


def is_question_only(text: str) -> bool:
    """True when every sentence asks something. A question is not evidence for a finding or a negative."""
    parts = sentences(text)
    return bool(parts) and all(part.endswith(("?", "؟")) for part in parts)


def normalize(text: str) -> str:
    """Lowercase, no punctuation, single spaces: for comparing what was said with what was written."""
    return " ".join(_PUNCT_RE.sub(" ", text.lower()).split())
