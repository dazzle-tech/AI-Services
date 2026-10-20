"""Raw int16 PCM from the browser to 16 kHz mono float32 (what Whisper reads)."""

from __future__ import annotations

import numpy as np

TARGET_SR = 16000


def pcm_to_float32(data: bytes, sample_rate: int, channels: int = 1) -> np.ndarray:
    """`data` must hold whole sample frames (a multiple of 2 * channels bytes)."""
    if not data:
        return np.zeros(0, dtype=np.float32)
    pcm = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1)
    if sample_rate != TARGET_SR:
        pcm = _resample_linear(pcm, sample_rate, TARGET_SR)
    return pcm.astype(np.float32, copy=False)


def _resample_linear(samples: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr or samples.size == 0:
        return samples
    duration = samples.size / src_sr
    n_out = int(round(duration * dst_sr))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    src_t = np.linspace(0.0, duration, num=samples.size, endpoint=False)
    dst_t = np.linspace(0.0, duration, num=n_out, endpoint=False)
    return np.interp(dst_t, src_t, samples).astype(np.float32)
