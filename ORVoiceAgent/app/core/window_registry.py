"""Same eight window paths as ORDisplayPlugin: window_id + DisplayPlugin path + default role."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WindowSpec:
    window_id: str
    route: str
    display_path: str
    role: str


# EMR UI: main tab "Nursing" with four sub-tabs (paths under /windows/nursing/…).
NURSING_SUB_TABS = (
    ("Verification of Marking Site", "/windows/nursing/verification-of-marking-site"),
    ("Time Out", "/windows/nursing/time-out"),
    ("Intraoperative", "/windows/nursing/intraoperative"),
    ("Sign Out", "/windows/nursing/sign-out"),
)

ANESTHESIA_SUB_TABS = (
    ("Pre-Anesthesia Evaluation Record & Anesthesia Plan", "/windows/anesthesia/pre-evaluation-plan"),
    ("Induction Assessment and Intraoperative Anesthesia", "/windows/anesthesia/induction-intraoperative"),
    ("Patient observation and Drugs", "/windows/anesthesia/observation-drugs"),
)

OPERATIVE_NOTE_SUB_TABS = (
    ("Operative Note", "/windows/operative-note"),
)

WINDOWS: tuple[WindowSpec, ...] = (
    WindowSpec(
        "nursing_verification_of_marking_site",
        "/windows/nursing/verification-of-marking-site",
        "/api/v1/windows/nursing/verification-of-marking-site",
        "nurse",
    ),
    WindowSpec(
        "nursing_time_out",
        "/windows/nursing/time-out",
        "/api/v1/windows/nursing/time-out",
        "nurse",
    ),
    WindowSpec(
        "nursing_intraoperative",
        "/windows/nursing/intraoperative",
        "/api/v1/windows/nursing/intraoperative",
        "nurse",
    ),
    WindowSpec(
        "nursing_sign_out",
        "/windows/nursing/sign-out",
        "/api/v1/windows/nursing/sign-out",
        "nurse",
    ),
    WindowSpec(
        "anesthesia_pre_evaluation_plan",
        "/windows/anesthesia/pre-evaluation-plan",
        "/api/v1/windows/anesthesia/pre-evaluation-plan",
        "anesthetist",
    ),
    WindowSpec(
        "anesthesia_induction_intraoperative",
        "/windows/anesthesia/induction-intraoperative",
        "/api/v1/windows/anesthesia/induction-intraoperative",
        "anesthetist",
    ),
    WindowSpec(
        "anesthesia_observation_drugs",
        "/windows/anesthesia/observation-drugs",
        "/api/v1/windows/anesthesia/observation-drugs",
        "anesthetist",
    ),
    WindowSpec(
        "operative_note",
        "/windows/operative-note",
        "/api/v1/windows/operative-note",
        "surgeon",
    ),
)

WINDOW_BY_ID = {item.window_id: item for item in WINDOWS}
