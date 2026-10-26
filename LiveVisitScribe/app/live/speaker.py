"""First speaker label, from the words, until the picked-up model assigns one.

One microphone cannot reliably separate two voices, so this is a guess and never diarization. A
finished line keeps this label only until the model returns a speaker for that id. The chart note
still comes from ConvoVoiceAgent POST /api/v1/draft after Stop.
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
    r"\b(?:i have|i've|i had|i feel|i am having|i was worried|i'm worried|i take|i took|it hurts|"
    r"it has been|it's been|shall i|is my|my|"
    r"عندي|أشعر|اشعر|تعبان|بيوجعني)\b",
    re.IGNORECASE,
)
# "Doctor," at the start of a turn is the patient speaking to the clinician. "I am Dr Patel" is not.
_ADDRESS_DOCTOR_RE = re.compile(r"(?:^|[,;]\s*)(?:dr|doctor)\b", re.IGNORECASE)
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
    elif _ADDRESS_DOCTOR_RE.search(text):
        patient += 2
    if re.search(r"\b(?:shall i|is my)\b", text, re.IGNORECASE):
        patient += 2
    if doctor > patient:
        return "doctor"
    return "patient"
