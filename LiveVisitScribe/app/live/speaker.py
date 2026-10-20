"""Best-effort speaker label from the words of a line.

One microphone cannot reliably separate two voices, so this is a guess and never diarization. Lines
with no clear markers stay "unknown". The authoritative speaker roles are produced after Stop by
ConvoVoiceAgent POST /api/v1/draft.
"""

from __future__ import annotations

import re

from app.live.text_utils import sentences

_DOCTOR_RE = re.compile(
    r"\b(?:let me (?:examine|check|listen)|i will record|i'll record|we'll|we will|i recommend|"
    r"i'd like to|tell me|what brings|how long|how many|how often|do you|are you|have you|can you|"
    r"any|blood pressure is|your (?:blood pressure|temperature|pulse)|"
    r"هل|كم|منذ متى|ما الذي|ماذا|خلني|سأفحص|لنقم)\b",
    re.IGNORECASE,
)
_PATIENT_RE = re.compile(
    r"\b(?:i have|i've|i had|i feel|i am having|i take|i took|it hurts|it has been|it's been|my|"
    r"عندي|أشعر|اشعر|تعبان|بيوجعني)\b",
    re.IGNORECASE,
)
_ANSWER_RE = re.compile(r"^(?:no|yes|mild|severe|a little|worse|better|sometimes|لا|نعم)\b", re.IGNORECASE)
_INTRODUCTION_RE = re.compile(r"\bi(?: am|'m) (?:dr|doctor)\b", re.IGNORECASE)


def guess_speaker(text: str) -> str:
    doctor = len(_DOCTOR_RE.findall(text))
    patient = len(_PATIENT_RE.findall(text))
    parts = sentences(text)
    asked = [part.endswith(("?", "؟")) for part in parts]
    if asked and all(asked):
        doctor += 2
    elif any(asked):
        doctor += 1
    if _ANSWER_RE.match(text.strip()):
        patient += 1
    if _INTRODUCTION_RE.search(text):
        doctor += 2
    if doctor > patient:
        return "doctor"
    if patient > doctor:
        return "patient"
    return "unknown"
