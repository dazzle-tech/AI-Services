"""Basic audio pre-processing for noisy OR environments."""

from __future__ import annotations

import io
import struct
import wave
from typing import Tuple


def preprocess_audio(audio_bytes: bytes, filename: str) -> bytes:
    """
    Apply band-pass filtering tuned for speech (300–3400 Hz) and light noise reduction.
    Returns WAV bytes suitable for transcription backends.
    """
    try:
        import numpy as np
        from scipy import signal
    except ImportError:
        return audio_bytes

    samples, sample_rate = _load_wav_samples(audio_bytes, filename)
    if samples is None or len(samples) == 0:
        return audio_bytes

    nyquist = sample_rate / 2
    low = 300 / nyquist
    high = min(3400 / nyquist, 0.99)
    b, a = signal.butter(4, [low, high], btype="band")
    filtered = signal.filtfilt(b, a, samples)

    # Simple noise gate: attenuate very quiet frames
    rms = np.sqrt(np.mean(filtered**2))
    if rms > 0:
        threshold = rms * 0.15
        filtered = np.where(np.abs(filtered) < threshold, filtered * 0.1, filtered)

    return _samples_to_wav(filtered, sample_rate)


def _load_wav_samples(audio_bytes: bytes, filename: str) -> Tuple["object", int] | Tuple[None, int]:
    import numpy as np

    if filename.lower().endswith(".wav"):
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
                sample_rate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())
                if wav.getsampwidth() == 2:
                    samples = np.array(struct.unpack(f"<{len(frames)//2}h", frames), dtype=np.float32)
                    samples /= 32768.0
                    if wav.getnchannels() == 2:
                        samples = samples.reshape(-1, 2).mean(axis=1)
                    return samples, sample_rate
        except Exception:
            pass

    # Non-WAV or unreadable — return None to skip preprocessing
    return None, 0


def _samples_to_wav(samples, sample_rate: int) -> bytes:
    import numpy as np

    clipped = np.clip(samples, -1.0, 1.0)
    int_samples = (clipped * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(int_samples.tobytes())
    return buffer.getvalue()
