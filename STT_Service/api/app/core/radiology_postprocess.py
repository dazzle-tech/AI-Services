"""Lightweight post-processor for radiology-specific transcription fixes.

The lexicon prompt biases the decoder, but Whisper still tends to break
sequence-style terms (e.g. "T 1 weighted" instead of "T1-weighted").
This module applies regex-based normalization on the decoded text.
"""
from __future__ import annotations

import re
from typing import Iterable, Tuple

# (pattern, replacement) -- order matters: most specific first.
_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    # MRI sequence formatting: "T 1 weighted" / "t1 weighted" -> "T1-weighted"
    (re.compile(r"\bT\s*([12])\s*[-]?\s*weighted\b", re.IGNORECASE), r"T\1-weighted"),
    # FLAIR / DWI / ADC / STIR are routinely capitalized
    (re.compile(r"\bflair\b"), "FLAIR"),
    (re.compile(r"\bDw\s*i\b|\bdwi\b"), "DWI"),
    (re.compile(r"\badc\b"), "ADC"),
    (re.compile(r"\bstir\b"), "STIR"),
    # Modality acronyms
    (re.compile(r"\bct\s*scan\b", re.IGNORECASE), "CT scan"),
    (re.compile(r"\bmri\b", re.IGNORECASE), "MRI"),
    (re.compile(r"\bpet[-\s]?ct\b", re.IGNORECASE), "PET-CT"),
    (re.compile(r"\bspect\b", re.IGNORECASE), "SPECT"),
    (re.compile(r"\bx[-\s]?ray\b", re.IGNORECASE), "X-ray"),
    # Contrast phrasing
    (re.compile(r"\bnon\s*contrast\b", re.IGNORECASE), "non-contrast"),
    (re.compile(r"\bcontrast\s*enhanced\b", re.IGNORECASE), "contrast-enhanced"),
    # Ground-glass
    (re.compile(r"\bground\s*glass\s*opacit(y|ies)\b", re.IGNORECASE), r"ground-glass opacit\1"),
    # Common echogenicity terms (already lowercase)
    (re.compile(r"\bhyper\s+echoic\b", re.IGNORECASE), "hyperechoic"),
    (re.compile(r"\bhypo\s+echoic\b", re.IGNORECASE), "hypoechoic"),
    (re.compile(r"\biso\s+echoic\b", re.IGNORECASE), "isoechoic"),
    (re.compile(r"\ban\s+echoic\b", re.IGNORECASE), "anechoic"),
    # Measurements: "5 millimeters" -> "5 mm"; "2.5 centimeters" -> "2.5 cm"
    (re.compile(r"(\d+(?:\.\d+)?)\s*millimet(?:re|er)s?\b", re.IGNORECASE), r"\1 mm"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*centimet(?:re|er)s?\b", re.IGNORECASE), r"\1 cm"),
    # Number-x-number lesion sizes: "2 by 3" -> "2 x 3"
    (re.compile(r"(\d+(?:\.\d+)?)\s+by\s+(\d+(?:\.\d+)?)\b", re.IGNORECASE), r"\1 x \2"),
    # Collapse double spaces from substitutions
    (re.compile(r"[ \t]{2,}"), " "),
)


def normalize_radiology_text(text: str) -> str:
    if not text:
        return text
    out = text
    for pat, repl in _PATTERNS:
        out = pat.sub(repl, out)
    return out.strip()


def normalize_segments(segments: Iterable[dict]) -> list[dict]:
    """Apply normalization to each segment's text in-place (returns new list)."""
    result = []
    for s in segments:
        s2 = dict(s)
        s2["text"] = normalize_radiology_text(s2.get("text", ""))
        result.append(s2)
    return result
