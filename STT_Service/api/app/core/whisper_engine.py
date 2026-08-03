"""Thin wrapper around faster-whisper for radiology STT.

Loads the model once and exposes transcription methods for both file paths
and raw PCM numpy arrays (used by the streaming endpoint).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

import numpy as np

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class Segment:
    id: int
    start: float
    end: float
    text: str
    avg_logprob: float
    no_speech_prob: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
            "avg_logprob": round(self.avg_logprob, 4),
            "no_speech_prob": round(self.no_speech_prob, 4),
        }


@dataclass
class TranscriptionResult:
    text: str
    language: str
    language_probability: float
    duration_audio_s: float
    duration_inference_s: float
    segments: List[Segment] = field(default_factory=list)
    model: str = ""
    device: str = ""

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "language": self.language,
            "language_probability": round(self.language_probability, 4),
            "audio_duration_seconds": round(self.duration_audio_s, 3),
            "inference_seconds": round(self.duration_inference_s, 3),
            "segments": [s.to_dict() for s in self.segments],
            "model": self.model,
            "device": self.device,
        }


def _resolve_device_and_compute(settings: Settings) -> tuple[str, str]:
    """Pick (device, compute_type) honoring overrides and CUDA availability."""
    device_pref = settings.whisper_device or "auto"

    cuda_available = False
    if device_pref in ("auto", "cuda"):
        try:
            # Lightweight CUDA probe via torch if installed; otherwise fall back to ctranslate2.
            try:
                import torch  # type: ignore
                cuda_available = bool(torch.cuda.is_available())
            except Exception:
                import ctranslate2  # type: ignore
                cuda_available = "cuda" in ctranslate2.get_supported_compute_types("cuda")  # type: ignore[arg-type]
        except Exception:
            cuda_available = False

    if device_pref == "cuda" and not cuda_available:
        logger.warning("WHISPER_DEVICE=cuda but CUDA not available; falling back to CPU.")
        device = "cpu"
    elif device_pref == "auto":
        device = "cuda" if cuda_available else "cpu"
    else:
        device = device_pref

    compute_type = settings.whisper_compute_type
    if not compute_type:
        compute_type = "float16" if device == "cuda" else "int8"
    return device, compute_type


class WhisperEngine:
    """Threadsafe singleton-ish Whisper wrapper. Instance is created once at app startup."""

    def __init__(self, settings: Settings):
        from faster_whisper import WhisperModel  # imported lazily so tests can mock

        self.settings = settings
        self.device, self.compute_type = _resolve_device_and_compute(settings)
        self.model_name = settings.whisper_model
        self.initial_prompt = settings.load_radiology_prompt() or None
        self._lock = threading.Lock()

        logger.info(
            "Loading Whisper model=%s device=%s compute_type=%s",
            self.model_name, self.device, self.compute_type,
        )
        kwargs = {}
        if settings.whisper_model_cache:
            kwargs["download_root"] = settings.whisper_model_cache

        self._model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
            **kwargs,
        )
        logger.info("Whisper model loaded.")

    # ---- public API ---------------------------------------------------

    def transcribe_file(
        self,
        path: str,
        *,
        language: Optional[str] = None,
        beam_size: int = 5,
        extra_prompt: Optional[str] = None,
    ) -> TranscriptionResult:
        return self._transcribe(path, language=language, beam_size=beam_size, extra_prompt=extra_prompt)

    def transcribe_audio_array(
        self,
        pcm_f32: np.ndarray,
        *,
        language: Optional[str] = None,
        beam_size: int = 5,
        extra_prompt: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe a numpy float32 mono 16kHz array."""
        if pcm_f32.dtype != np.float32:
            pcm_f32 = pcm_f32.astype(np.float32)
        return self._transcribe(pcm_f32, language=language, beam_size=beam_size, extra_prompt=extra_prompt)

    # ---- internals ----------------------------------------------------

    def _transcribe(
        self,
        audio,
        *,
        language: Optional[str],
        beam_size: int,
        extra_prompt: Optional[str],
    ) -> TranscriptionResult:
        lang = language or self.settings.whisper_language or None

        prompt = self.initial_prompt or ""
        if extra_prompt:
            prompt = (prompt + " " + extra_prompt).strip() if prompt else extra_prompt

        t0 = time.perf_counter()
        with self._lock:
            segments_iter, info = self._model.transcribe(
                audio,
                language=lang,
                beam_size=beam_size,
                initial_prompt=prompt or None,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
                condition_on_previous_text=True,
                temperature=[0.0, 0.2, 0.4],
                word_timestamps=False,
            )
            segments = self._materialize(segments_iter)
        elapsed = time.perf_counter() - t0

        full_text = " ".join(s.text.strip() for s in segments).strip()
        return TranscriptionResult(
            text=full_text,
            language=info.language,
            language_probability=float(info.language_probability),
            duration_audio_s=float(info.duration),
            duration_inference_s=elapsed,
            segments=segments,
            model=self.model_name,
            device=self.device,
        )

    @staticmethod
    def _materialize(segments_iter: Iterable) -> List[Segment]:
        out: List[Segment] = []
        for i, s in enumerate(segments_iter):
            out.append(
                Segment(
                    id=i,
                    start=float(s.start),
                    end=float(s.end),
                    text=s.text.strip(),
                    avg_logprob=float(getattr(s, "avg_logprob", 0.0) or 0.0),
                    no_speech_prob=float(getattr(s, "no_speech_prob", 0.0) or 0.0),
                )
            )
        return out
