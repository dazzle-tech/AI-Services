"""FFmpeg-backed audio normalization.

Whisper expects 16 kHz mono PCM. Clients may send wav/mp3/m4a/webm/ogg/flac,
so we decode and resample uniformly with FFmpeg.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Tuple

import numpy as np

logger = logging.getLogger(__name__)

TARGET_SR = 16000


class FFmpegNotInstalledError(RuntimeError):
    pass


class AudioDecodeError(RuntimeError):
    pass


def _ensure_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FFmpegNotInstalledError(
            "ffmpeg not found on PATH. Install FFmpeg (https://ffmpeg.org/download.html) "
            "and ensure it is available on the system PATH."
        )
    return path


def decode_to_pcm_f32(audio_bytes: bytes, input_hint: str | None = None) -> np.ndarray:
    """Decode an arbitrary container/codec to 16 kHz mono float32 PCM in [-1, 1].

    Uses ffmpeg as a subprocess reading from stdin and emitting PCM on stdout.
    """
    ffmpeg = _ensure_ffmpeg()

    cmd = [
        ffmpeg,
        "-hide_banner", "-loglevel", "error",
        "-nostdin",
        "-i", "pipe:0",
        "-f", "s16le",     # signed 16-bit little-endian PCM
        "-ac", "1",        # mono
        "-ar", str(TARGET_SR),
        "pipe:1",
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=audio_bytes,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise FFmpegNotInstalledError(str(e)) from e

    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="ignore").strip()
        raise AudioDecodeError(f"FFmpeg failed (input_hint={input_hint!r}): {err or 'unknown error'}")

    pcm_i16 = np.frombuffer(proc.stdout, dtype=np.int16)
    if pcm_i16.size == 0:
        raise AudioDecodeError("FFmpeg produced empty output (silent or corrupted audio?)")

    return (pcm_i16.astype(np.float32) / 32768.0)


def pcm_bytes_to_array(pcm_bytes: bytes, sample_rate: int, channels: int = 1) -> np.ndarray:
    """Convert raw int16 PCM bytes (as commonly produced by mic capture) to 16 kHz mono f32.

    No FFmpeg call needed for the common case (sr=16000, channels=1).
    """
    if not pcm_bytes:
        return np.zeros(0, dtype=np.float32)
    pcm = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1)
    if sample_rate != TARGET_SR:
        pcm = _resample_linear(pcm, sample_rate, TARGET_SR)
    return pcm.astype(np.float32, copy=False)


def _resample_linear(x: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Cheap linear resampler (sufficient for short streaming chunks)."""
    if src_sr == dst_sr or x.size == 0:
        return x
    duration = x.size / src_sr
    n_out = int(round(duration * dst_sr))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    src_t = np.linspace(0.0, duration, num=x.size, endpoint=False)
    dst_t = np.linspace(0.0, duration, num=n_out, endpoint=False)
    return np.interp(dst_t, src_t, x).astype(np.float32)


def audio_duration_seconds(pcm_f32: np.ndarray) -> float:
    return float(pcm_f32.size) / float(TARGET_SR)
