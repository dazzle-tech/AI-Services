"""Real-time WebSocket transcription.

Protocol
--------
Client -> Server (text frames, JSON):
    {"type": "start", "sample_rate": 16000, "channels": 1,
     "language": "en", "extra_prompt": "chest CT, 45M"}
    {"type": "stop"}

Client -> Server (binary frames):
    raw little-endian int16 PCM samples (mono unless channels>1 declared in `start`)

Server -> Client (text frames, JSON):
    {"type": "ready", "sample_rate": 16000, "model": "...", "device": "..."}
    {"type": "partial", "text": "<rolling transcript>", "raw_text": "...", "window_text": "<just this window>", "audio_seconds_processed": ..., "inference_seconds": ...}
    {"type": "final", "text": "...", "raw_text": "...", "audio_seconds": ..., "segments": [...]}
    {"type": "error", "detail": "..."}
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.audio_processor import TARGET_SR, pcm_bytes_to_array
from app.core.radiology_postprocess import normalize_radiology_text, normalize_segments

logger = logging.getLogger(__name__)

router = APIRouter(tags=["streaming"])


class _StreamState:
    """Buffers incoming PCM and produces rolling-window transcriptions."""

    def __init__(self, *, sample_rate: int, channels: int, chunk_s: float, overlap_s: float):
        self.client_sr = sample_rate
        self.channels = channels
        self.chunk_samples = int(TARGET_SR * chunk_s)
        self.overlap_samples = int(TARGET_SR * overlap_s)
        self.buffer = np.zeros(0, dtype=np.float32)   # accumulator (at TARGET_SR)
        self.full_audio: list[np.ndarray] = []        # everything we've received, for the final pass
        self.committed_text = ""                      # rolling transcript from earlier windows
        self.audio_seconds_committed = 0.0

    def commit_window_text(self, text: str) -> str:
        """Append a freshly transcribed window to the rolling transcript and return it."""
        text = (text or "").strip()
        if text:
            self.committed_text = f"{self.committed_text} {text}".strip()
        return self.committed_text

    def feed(self, pcm_bytes: bytes) -> None:
        arr = pcm_bytes_to_array(pcm_bytes, self.client_sr, self.channels)
        if arr.size == 0:
            return
        self.buffer = np.concatenate([self.buffer, arr])
        self.full_audio.append(arr)

    def has_chunk_ready(self) -> bool:
        return self.buffer.size >= self.chunk_samples

    def pop_chunk(self) -> np.ndarray:
        """Return next analysis window, keeping `overlap_samples` for the next pass."""
        end = self.chunk_samples
        window = self.buffer[:end].copy()
        # Keep overlap for context continuity
        keep_from = max(0, end - self.overlap_samples)
        self.buffer = self.buffer[keep_from:].copy()
        self.audio_seconds_committed += (end - max(0, self.overlap_samples)) / TARGET_SR
        return window

    def remaining(self) -> np.ndarray:
        return self.buffer.copy()

    def all_audio(self) -> np.ndarray:
        if not self.full_audio:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self.full_audio)


@router.websocket("/api/v1/ws/transcribe")
async def websocket_transcribe(ws: WebSocket):
    await ws.accept()
    settings = ws.app.state.settings
    engine = getattr(ws.app.state, "whisper_engine", None)
    if engine is None:
        await ws.send_text(json.dumps({"type": "error", "detail": "Whisper model not loaded."}))
        await ws.close(code=1011)
        return

    state: _StreamState | None = None
    language: str | None = None
    extra_prompt: str | None = None
    started = False

    try:
        # Wait for a 'start' control message before accepting audio.
        await ws.send_text(json.dumps({
            "type": "hello",
            "expects": "send JSON {'type':'start', 'sample_rate':16000, 'channels':1, ...} then binary int16 PCM frames",
            "model": engine.model_name,
            "device": engine.device,
        }))

        while True:
            msg = await ws.receive()
            # Disconnect frames
            if msg.get("type") == "websocket.disconnect":
                break

            text = msg.get("text")
            data = msg.get("bytes")

            if text is not None:
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    await ws.send_text(json.dumps({"type": "error", "detail": "Invalid JSON control message."}))
                    continue

                mtype = (payload.get("type") or "").lower()
                if mtype == "start":
                    sr = int(payload.get("sample_rate") or TARGET_SR)
                    ch = int(payload.get("channels") or 1)
                    language = payload.get("language") or settings.whisper_language
                    extra_prompt = payload.get("extra_prompt")
                    state = _StreamState(
                        sample_rate=sr, channels=ch,
                        chunk_s=settings.stream_chunk_seconds,
                        overlap_s=settings.stream_overlap_seconds,
                    )
                    started = True
                    await ws.send_text(json.dumps({
                        "type": "ready",
                        "sample_rate": sr,
                        "channels": ch,
                        "model": engine.model_name,
                        "device": engine.device,
                        "chunk_seconds": settings.stream_chunk_seconds,
                        "overlap_seconds": settings.stream_overlap_seconds,
                    }))
                elif mtype == "stop":
                    break
                else:
                    await ws.send_text(json.dumps({"type": "error", "detail": f"Unknown control type: {mtype}"}))

            elif data is not None:
                if not started or state is None:
                    await ws.send_text(json.dumps({"type": "error", "detail": "Send 'start' before audio."}))
                    continue
                state.feed(data)

                # Flush as many windows as we have buffered.
                while state.has_chunk_ready():
                    window = state.pop_chunk()
                    t0 = time.perf_counter()
                    # Run blocking inference in a thread so the event loop stays responsive.
                    result = await asyncio.to_thread(
                        engine.transcribe_audio_array,
                        window,
                        language=language,
                        beam_size=1,
                        extra_prompt=extra_prompt,
                    )
                    inf = time.perf_counter() - t0
                    window_text = result.text
                    rolling = state.commit_window_text(window_text)
                    await ws.send_text(json.dumps({
                        "type": "partial",
                        "text": normalize_radiology_text(rolling),
                        "raw_text": rolling,
                        "window_text": window_text,
                        "audio_seconds_processed": state.audio_seconds_committed,
                        "inference_seconds": round(inf, 3),
                    }))

        # --- finalization: re-run on entire audio for best quality ---
        if state is not None:
            full = state.all_audio()
            if full.size > 0:
                t0 = time.perf_counter()
                final = await asyncio.to_thread(
                    engine.transcribe_audio_array,
                    full,
                    language=language,
                    beam_size=5,
                    extra_prompt=extra_prompt,
                )
                raw_text = final.text
                segs = normalize_segments([s.to_dict() for s in final.segments])
                await ws.send_text(json.dumps({
                    "type": "final",
                    "text": normalize_radiology_text(raw_text),
                    "raw_text": raw_text,
                    "audio_seconds": final.duration_audio_s,
                    "inference_seconds": round(time.perf_counter() - t0, 3),
                    "segments": segs,
                    "model": final.model,
                    "device": final.device,
                }))

        await ws.close()

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as e:
        logger.exception("WebSocket transcription error")
        try:
            await ws.send_text(json.dumps({"type": "error", "detail": str(e)}))
            await ws.close(code=1011)
        except Exception:
            pass
