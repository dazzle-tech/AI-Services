"""Small text helpers shared by the live segments and the picked-up checks."""

from __future__ import annotations

import re

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_UTTERANCE_RE = re.compile(r"[^.!?؟]+[.!?؟]*")
_PUNCT_RE = re.compile(r"[^\w\s]")


def detect_lang(text: str) -> str:
    """en or ar only. Whichever script has more letters wins; Arabic wins a tie if any Arabic is present."""
    arabic = len(_ARABIC_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    if arabic == 0 and latin == 0:
        return "en"
    if arabic > latin:
        return "ar"
    if latin > arabic:
        return "en"
    return "ar" if arabic else "en"


def sentences(text: str) -> list[str]:
    return [part.strip() for part in _UTTERANCE_RE.findall(text) if part.strip()]


def is_question_only(text: str) -> bool:
    """True when every sentence asks something. A question is not evidence for a finding or a negative."""
    parts = sentences(text)
    return bool(parts) and all(part.endswith(("?", "؟")) for part in parts)


def normalize(text: str) -> str:
    """Lowercase, no punctuation, single spaces: for comparing what was said with what was written."""
    return " ".join(_PUNCT_RE.sub(" ", text.lower()).split())
