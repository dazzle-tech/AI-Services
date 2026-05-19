"""MRN extraction and normalization helpers."""

from __future__ import annotations

import re
from typing import Optional


# Common MRN phrases such as:
# - "MRN P104"
# - "mrn: p104"
# - "medical record number P104"
_MRN_PHRASE_RE = re.compile(
    r"\b(?:mrn|medical\s+record(?:\s+number)?|record)\b(?:\s*[:#]\s*|\s+)(?P<mrn>[A-Za-z0-9_-]{1,30})\b",
    re.IGNORECASE,
)

# Optional standalone MRN format support (project convention): "P104"
_STANDALONE_MRN_RE = re.compile(r"\bP\d{3,10}\b", re.IGNORECASE)


def normalize_mrn(mrn: str) -> str:
    """
    Normalize an MRN string for lookups.

    - Strips surrounding whitespace
    - Upper-cases
    - Removes internal whitespace
    """
    mrn_str = (mrn or "").strip()
    mrn_str = re.sub(r"\s+", "", mrn_str)
    return mrn_str.upper()


def extract_mrn(user_query: str, *, allow_standalone: bool = True) -> Optional[str]:
    """
    Extract a Medical Record Number (MRN) from a user query.

    Supports:
    - "MRN P104" / "mrn p104"
    - "medical record number P104"
    - Optionally: standalone "P104" (when allow_standalone=True)
    """
    text = (user_query or "").strip()
    if not text:
        return None

    m = _MRN_PHRASE_RE.search(text)
    if m:
        mrn = m.group("mrn")
        mrn_norm = normalize_mrn(mrn)
        return mrn_norm or None

    if allow_standalone:
        m2 = _STANDALONE_MRN_RE.search(text)
        if m2:
            return normalize_mrn(m2.group(0)) or None

    return None
