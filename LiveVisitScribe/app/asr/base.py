from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class AsrResult:
    text: str


class Transcriber(Protocol):
    name: str

    def transcribe(self, audio: np.ndarray, *, turn_index: int, final: bool) -> AsrResult:
        """Blocking call (runs in a worker thread). `audio` is 16 kHz mono float32.

        `turn_index` is the number of lines already finalized, so a partial and the final pass of the
        same line get the same value. `final` is False for a rolling partial.
        """
        ...
