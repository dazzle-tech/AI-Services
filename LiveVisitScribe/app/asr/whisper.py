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


def keep_segment(segment: object, settings: Settings) -> bool:
    """Drop a repeated hallucination or a piece that is both non-speech and a poor fit. Missing scores stay."""
    ratio = getattr(segment, "compression_ratio", None)
    if ratio is not None and ratio > settings.whisper_max_compression_ratio:
        return False
    no_speech = getattr(segment, "no_speech_prob", None)
    avg_logprob = getattr(segment, "avg_logprob", None)
    if (
        no_speech is not None
        and avg_logprob is not None
        and no_speech > settings.whisper_no_speech_threshold
        and avg_logprob < settings.whisper_min_avg_logprob
    ):
        return False
    return True


def low_confidence_numbers(segment: object, threshold: float) -> list[str]:
    """Digit-bearing words whose probability is below the threshold, punctuation stripped."""
    found: list[str] = []
    for word in getattr(segment, "words", None) or []:
        raw = str(getattr(word, "word", "") or "")
        token = raw.strip().strip(".,;:!?؟،\"'()[]")
        probability = getattr(word, "probability", None)
        if not token or probability is None or probability >= threshold:
            continue
        if any(character.isdigit() for character in token):
            found.append(token)
    return found


def pick_language(info: object, allowed: list[str]) -> str | None:
    """None when the detected language is allowed (or nothing is allowed). Otherwise the best allowed code."""
    allowed = [code.strip() for code in allowed if code and code.strip()]
    detected = getattr(info, "language", None)
    if not allowed or detected in allowed:
        return None
    best_code: str | None = None
    best_probability = float("-inf")
    permitted = set(allowed)
    for item in getattr(info, "all_language_probs", None) or []:
        code, probability = item[0], float(item[1])
        if code in permitted and probability > best_probability:
            best_code = code
            best_probability = probability
    return best_code


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
        self._settings = settings
        self._language = settings.whisper_language or None
        self._lock = threading.Lock()  # one model, possibly several sockets: run one pass at a time
        kwargs = {"download_root": settings.whisper_model_cache} if settings.whisper_model_cache else {}
        logger.info("Loading Whisper model=%s device=%s compute=%s", self.model_name, self.device, self.compute_type)
        self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type, **kwargs)
        logger.info("Whisper model loaded")

    def _pass(self, audio: np.ndarray, *, language: str | None, final: bool, word_timestamps: bool):
        prompt = (self._settings.whisper_initial_prompt or "").strip() or None
        return self._model.transcribe(
            audio,
            language=language,
            initial_prompt=prompt,
            beam_size=3 if final else 1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
            condition_on_previous_text=False,
            temperature=0.0,
            word_timestamps=word_timestamps,
        )

    def transcribe(self, audio: np.ndarray, *, turn_index: int, final: bool) -> AsrResult:
        samples = audio.astype(np.float32, copy=False)
        word_timestamps = bool(self._settings.whisper_word_confidence)
        with self._lock:
            segments, info = self._pass(samples, language=self._language, final=final, word_timestamps=word_timestamps)
            if self._language is None:
                chosen = pick_language(info, self._settings.whisper_language_list)
                if chosen:
                    segments, info = self._pass(samples, language=chosen, final=final, word_timestamps=word_timestamps)
            kept = [segment for segment in segments if keep_segment(segment, self._settings)]
            numbers: list[str] = []
            if word_timestamps:
                for segment in kept:
                    numbers.extend(low_confidence_numbers(segment, self._settings.whisper_low_confidence))
            text = " ".join(segment.text.strip() for segment in kept)
        return AsrResult(text=" ".join(text.split()), low_confidence=numbers)
