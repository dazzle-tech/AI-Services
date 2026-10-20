"""Deterministic transcriber for USE_LLM_STUB=true: no Whisper, no download.

It ignores the audio content and returns scripted lines in order, one per spoken line. The partial
pass returns the first half of the words, so the partial-then-final flow can be tested.
"""

from __future__ import annotations

import numpy as np

from app.asr.base import AsrResult

DEFAULT_SCRIPT = (
    "Good morning, what brings you in today?",
    "I have had a daily headache for two weeks.",
    "Any nausea, or visual aura before the pain?",
    "Mild nausea in the mornings. No aura.",
    "How many Neurofen do you take?",
    "About three tablets a day.",
    "Let me examine you. Blood pressure is 128 over 82. Neuro exam is normal.",
)


class StubTranscriber:
    name = "stub"

    def __init__(self, script: tuple[str, ...] = DEFAULT_SCRIPT) -> None:
        self.script = tuple(script)

    def transcribe(self, audio: np.ndarray, *, turn_index: int, final: bool) -> AsrResult:
        line = self.script[turn_index % len(self.script)]
        if final:
            return AsrResult(text=line)
        words = line.split()
        return AsrResult(text=" ".join(words[: max(1, (len(words) + 1) // 2)]))
