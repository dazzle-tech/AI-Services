"""faster-whisper wrapper. Plain transcription: no domain lexicon, no text normalisation."""

from __future__ import annotations

import threading

import numpy as np

from app.asr.base import AsrResult
from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _register_cuda_dlls() -> None:
    """Make the pip CUDA 12 libraries visible. Windows does not search site-packages for cublas64_12.dll."""
    import os
    import sys
    from pathlib import Path

    for entry in sys.path:
        root = Path(entry)
        for name in ("nvidia/cublas/bin", "nvidia/cudnn/bin"):
            folder = root / name
            if not folder.is_dir():
                continue
            try:
                os.add_dll_directory(str(folder))
            except (AttributeError, OSError):
                pass
            os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")


def _resolve_device(preference: str) -> str:
    preference = (preference or "auto").lower()
    if preference != "auto":
        return preference
    try:
        import ctranslate2

        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        return "cpu"


class WhisperTranscriber:
    name = "whisper"

    def __init__(self, settings: Settings) -> None:
        from faster_whisper import WhisperModel  # lazy: not needed for the stub or the tests

        self.device = _resolve_device(settings.whisper_device)
        if self.device == "cuda":
            _register_cuda_dlls()
        self.compute_type = settings.whisper_compute_type or ("float16" if self.device == "cuda" else "int8")
        self.model_name = settings.whisper_model
        self._language = settings.whisper_language or None
        self._lock = threading.Lock()  # one model, possibly several sockets: run one pass at a time
        kwargs = {"download_root": settings.whisper_model_cache} if settings.whisper_model_cache else {}
        logger.info("Loading Whisper model=%s device=%s compute=%s", self.model_name, self.device, self.compute_type)
        self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type, **kwargs)
        logger.info("Whisper model loaded")

    def transcribe(self, audio: np.ndarray, *, turn_index: int, final: bool) -> AsrResult:
        with self._lock:
            segments, _info = self._model.transcribe(
                audio.astype(np.float32, copy=False),
                language=self._language,
                beam_size=3 if final else 1,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
                condition_on_previous_text=False,
                temperature=0.0,
                word_timestamps=False,
            )
            text = " ".join(segment.text.strip() for segment in segments)
        return AsrResult(text=" ".join(text.split()))
