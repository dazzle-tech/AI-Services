from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


@dataclass
class AsrResult:
    text: str
    low_confidence: list[str] = field(default_factory=list)


class Transcriber(Protocol):
    name: str

    def transcribe(self, audio: np.ndarray, *, turn_index: int, final: bool) -> AsrResult:
        """Blocking call (runs in a worker thread). `audio` is 16 kHz mono float32.

        `turn_index` is the number of lines already finalized, so a partial and the final pass of the
        same line get the same value. `final` is False for a rolling partial. The default backend is
        OpenAI gpt-live-transcribe; the stub ignores the samples and returns scripted text.
        """
        ...
