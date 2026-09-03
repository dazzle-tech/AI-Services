"""Hyphenated URL paths ↔ underscore window_id values, plus role/window_name routing."""

from __future__ import annotations

import re
from typing import Dict, Tuple

from fastapi import HTTPException

WINDOW_ID_TO_PATH = {
    "nursing_verification_of_marking_site": "/api/v1/windows/nursing/verification-of-marking-site",
    "nursing_time_out": "/api/v1/windows/nursing/time-out",
    "nursing_intraoperative": "/api/v1/windows/nursing/intraoperative",
    "nursing_sign_out": "/api/v1/windows/nursing/sign-out",
    "anesthesia_pre_evaluation_plan": "/api/v1/windows/anesthesia/pre-evaluation-plan",
    "anesthesia_induction_intraoperative": "/api/v1/windows/anesthesia/induction-intraoperative",
    "anesthesia_observation_drugs": "/api/v1/windows/anesthesia/observation-drugs",
    "operative_note": "/api/v1/windows/operative-note",
}

WINDOW_IDS = tuple(WINDOW_ID_TO_PATH.keys())

# EMR UI: main tab "Nursing" with four sub-tabs (all map to role nurse / paths under /windows/nursing/…).
NURSING_TAB = {
    "tab_name": "Nursing",
    "role": "nurse",
    "sub_tabs": (
        "Verification of Marking Site",
        "Time Out",
        "Intraoperative",
        "Sign Out",
    ),
}

_ROLE_WINDOW: Dict[Tuple[str, str], str] = {
    ("nurse", "verification of marking site"): "nursing_verification_of_marking_site",
    ("nurse", "sign in"): "nursing_verification_of_marking_site",
    ("nurse", "time out"): "nursing_time_out",
    ("nurse", "intraoperative"): "nursing_intraoperative",
    ("nurse", "sign out"): "nursing_sign_out",
    ("anesthetist", "pre anesthesia evaluation record and anesthesia plan"): "anesthesia_pre_evaluation_plan",
    ("anesthetist", "induction assessment and intraoperative anesthesia"): "anesthesia_induction_intraoperative",
    ("anesthetist", "patient observation and drugs"): "anesthesia_observation_drugs",
    ("surgeon", "operative note"): "operative_note",
}

_ROLE_ALIASES = {
    "nurse": "nurse",
    "nursing": "nurse",
    "anesthetist": "anesthetist",
    "anaesthetist": "anesthetist",
    "anesthesia": "anesthetist",
    "anesthesia record": "anesthetist",
    "surgeon": "surgeon",
    "operative note": "surgeon",
}

_PAIR_ALIASES = {
    ("nurse", "who sign in"): "nursing_verification_of_marking_site",
    ("nurse", "timeout"): "nursing_time_out",
    ("nurse", "who time out"): "nursing_time_out",
    ("nurse", "who sign out"): "nursing_sign_out",
    ("nurse", "intra op"): "nursing_intraoperative",
    ("anesthetist", "pre evaluation plan"): "anesthesia_pre_evaluation_plan",
    ("anesthetist", "induction"): "anesthesia_induction_intraoperative",
    ("anesthetist", "observation"): "anesthesia_observation_drugs",
}


def _normalize(value: str) -> str:
    text = (value or "").lower().strip()
    text = text.replace("&", " and ")
    text = text.replace("_", " ")
    text = text.replace("-", " ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_role(role: str) -> str:
    return _ROLE_ALIASES.get(_normalize(role), _normalize(role))


def role_for_window_id(window_id: str, role: str) -> str:
    canon = canonical_role(role)
    if canon in {"nurse", "anesthetist", "surgeon"}:
        return canon
    if window_id.startswith("nursing_"):
        return "nurse"
    if window_id.startswith("anesthesia_"):
        return "anesthetist"
    return "surgeon"


def resolve_window_id(role: str, window_name: str) -> str:
    """Pick which of the 8 window endpoints to fill from tab/role + sub-tab name."""
    raw_name = window_name or ""
    if "/" in raw_name:
        left, right = raw_name.split("/", 1)
        if not role:
            role = left.strip()
        window_name = right.strip()

    role_key = canonical_role(role)
    name_key = _normalize(window_name)

    if name_key in {"operative note", "op note", "operative notes"}:
        return "operative_note"

    slug = name_key.replace(" ", "_")
    if slug in WINDOW_ID_TO_PATH:
        return slug

    if (role_key, name_key) in _PAIR_ALIASES:
        return _PAIR_ALIASES[(role_key, name_key)]

    for (reg_role, reg_name), window_id in _ROLE_WINDOW.items():
        if reg_role == role_key and _normalize(reg_name) == name_key:
            return window_id

    raise HTTPException(
        status_code=422,
        detail={
            "message": f"Unknown (role, window_name): ({role!r}, {window_name!r})",
            "valid_pairs": sorted({f"{r} / {n}" for r, n in _ROLE_WINDOW}),
        },
    )
