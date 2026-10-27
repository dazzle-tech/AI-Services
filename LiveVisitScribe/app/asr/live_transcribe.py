"""OpenAI Realtime speech: gpt-live-transcribe over a transcription WebSocket.

Each live visit opens its own Realtime socket. Audio is appended as it arrives so transcript
deltas can stream out character by character. Local silence still ends a line: the session
commits the buffer and waits for the completed transcript.
"""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
from typing import Any, Optional
from urllib.parse import urlparse

import numpy as np

from app.asr.base import AsrResult
from app.audio.pcm import TARGET_SR, resample_linear
from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_LIVE_SR = 24000
_EV_DELTA = "conversation.item.input_audio_transcription.delta"
_EV_DONE = "conversation.item.input_audio_transcription.completed"
_APPEND_SAMPLES = 12_000  # ~0.5 s of 24 kHz PCM per append message


def _realtime_url(base_url: str) -> str:
    raw = (base_url or "https://api.openai.com/v1").rstrip("/")
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    scheme = "wss" if parsed.scheme in ("https", "wss", "") else "ws"
    path = parsed.path.rstrip("/")
    if path.endswith("/realtime"):
        root = path
    elif path.endswith("/v1"):
        root = f"{path}/realtime"
    elif path:
        root = f"{path}/v1/realtime"
    else:
        root = "/v1/realtime"
    netloc = parsed.netloc or "api.openai.com"
    return f"{scheme}://{netloc}{root}?intent=transcription"


def _float32_to_b64_pcm16(audio: np.ndarray) -> str:
    clipped = np.clip(audio.astype(np.float32, copy=False), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    return base64.b64encode(pcm.tobytes()).decode("ascii")


def _to_live_pcm(audio: np.ndarray) -> np.ndarray:
    if audio.size == 0:
        return audio.astype(np.float32, copy=False)
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)
    if TARGET_SR != _LIVE_SR:
        audio = resample_linear(audio, TARGET_SR, _LIVE_SR)
    return audio


def _session_config(settings: Settings) -> dict[str, Any]:
    transcription: dict[str, Any] = {
        "model": settings.live_transcribe_model,
        "delay": settings.live_transcribe_delay,
    }
    prompt = (settings.live_transcribe_prompt or settings.whisper_initial_prompt or "").strip()
    if prompt:
        transcription["prompt"] = prompt
    languages = settings.whisper_language_list
    if languages:
        transcription["languages"] = languages
    keywords = [
        item.strip()
        for item in settings.live_transcribe_keywords.split(",")
        if item.strip() and "<" not in item and ">" not in item
    ]
    if keywords:
        transcription["keywords"] = keywords
    return {
        "type": "transcription",
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": _LIVE_SR},
                "transcription": transcription,
                "turn_detection": None,
            }
        },
    }


def _error_detail(event: dict[str, Any]) -> str:
    err = event.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or err)
    return str(err or event)


class LiveTranscribeStream:
    """One Realtime transcription socket for a single live visit."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._url = _realtime_url(settings.openai_base_url)
        self._ws: Any = None
        self._reader: Optional[asyncio.Task] = None
        self._events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._text = ""
        self._final_text: Optional[str] = None
        self._waiting_commit = False

    @property
    def text(self) -> str:
        return self._text

    async def connect(self) -> None:
        if self._ws is not None:
            return
        import websockets

        self._ws = await websockets.connect(
            self._url,
            additional_headers={"Authorization": f"Bearer {self._settings.openai_api_key}"},
            open_timeout=self._settings.openai_timeout_seconds,
            close_timeout=5,
            max_size=8 * 1024 * 1024,
        )
        self._reader = asyncio.create_task(self._read_loop())
        await self._send({"type": "session.update", "session": _session_config(self._settings)})
        deadline = time.monotonic() + self._settings.openai_timeout_seconds
        while time.monotonic() < deadline:
            event = await self._next_event(deadline)
            kind = str(event.get("type") or "")
            if kind in {"session.created", "session.updated", "transcription_session.updated"}:
                return
            if kind == "error":
                raise RuntimeError(_error_detail(event))
        raise TimeoutError("Timed out waiting for the transcription session to start")

    async def begin_turn(self) -> None:
        """Clear the remote buffer and start a new spoken line."""
        await self.connect()
        self._text = ""
        self._final_text = None
        self._waiting_commit = False
        await self._send({"type": "input_audio_buffer.clear"})
        await self._drain()

    async def append(self, audio_16k: np.ndarray) -> str:
        """Push live audio and return the transcript text so far (may grow mid-call)."""
        await self.connect()
        live = _to_live_pcm(audio_16k)
        for start in range(0, live.size, _APPEND_SAMPLES):
            chunk = live[start : start + _APPEND_SAMPLES]
            await self._send(
                {
                    "type": "input_audio_buffer.append",
                    "audio": _float32_to_b64_pcm16(chunk),
                }
            )
        await self._drain()
        return self._text

    async def commit(self) -> str:
        """End the current line. Prefer the completed event; do not block the visit on it.

        gpt-live-transcribe often already streamed the line as deltas. Waiting a long time for
        `completed` stalls audio handling, fills the backlog, and the visit closes as overloaded.
        """
        await self.connect()
        self._waiting_commit = True
        prior = self._text
        self._final_text = None
        await self._send({"type": "input_audio_buffer.commit"})
        # Brief wait only. Live captioning must keep up with the microphone/WAV.
        wait_s = min(2.5, max(0.5, float(self._settings.openai_timeout_seconds)))
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if self._final_text is not None:
                text = self._final_text.strip() or self._text.strip() or prior.strip()
                self._waiting_commit = False
                return text
            await self._drain(wait=True, deadline=deadline)
        self._waiting_commit = False
        fallback = (self._text or prior).strip()
        if fallback:
            logger.info("gpt-live-transcribe commit used streamed text (no completed event yet)")
            return fallback
        return ""

    async def close(self) -> None:
        reader = self._reader
        self._reader = None
        if reader is not None:
            reader.cancel()
            try:
                await reader
            except asyncio.CancelledError:
                pass
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                event = json.loads(raw)
                if isinstance(event, dict):
                    await self._events.put(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._events.put({"type": "error", "error": {"message": str(exc)}})

    async def _drain(self, *, wait: bool = False, deadline: Optional[float] = None) -> None:
        while True:
            try:
                if wait:
                    remaining = max(0.05, (deadline or time.monotonic()) - time.monotonic())
                    event = await asyncio.wait_for(self._events.get(), timeout=remaining)
                else:
                    event = self._events.get_nowait()
            except (asyncio.QueueEmpty, asyncio.TimeoutError):
                return
            self._apply(event)

    async def _next_event(self, deadline: float) -> dict[str, Any]:
        remaining = max(0.05, deadline - time.monotonic())
        event = await asyncio.wait_for(self._events.get(), timeout=remaining)
        self._apply(event)
        return event

    def _apply(self, event: dict[str, Any]) -> None:
        kind = str(event.get("type") or "")
        if kind == _EV_DELTA:
            delta = str(event.get("delta") or "")
            if delta:
                # Some payloads send the growing string; others send only the new piece.
                if self._text and delta.startswith(self._text):
                    self._text = delta
                else:
                    self._text += delta
            return
        if kind == _EV_DONE:
            transcript = str(event.get("transcript") or "").strip()
            self._final_text = transcript or self._text
            if transcript:
                self._text = transcript
            return
        if kind in {"conversation.item.input_audio_transcription.failed", "transcription.failed"}:
            detail = _error_detail(event) if event.get("error") else str(event.get("message") or kind)
            raise RuntimeError(detail)
        if kind == "error":
            raise RuntimeError(_error_detail(event))

    async def _send(self, payload: dict[str, Any]) -> None:
        assert self._ws is not None
        await self._ws.send(json.dumps(payload))


class LiveTranscribeTranscriber:
    """Factory for per-visit streams. Also supports a blocking one-shot transcribe for tools."""

    name = "gpt-live-transcribe"

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for gpt-live-transcribe")
        self._settings = settings
        self._url = _realtime_url(settings.openai_base_url)
        self._lock = threading.Lock()
        logger.info("Speech: gpt-live-transcribe via %s", self._url.split("?", 1)[0])

    def open_stream(self) -> LiveTranscribeStream:
        return LiveTranscribeStream(self._settings)

    def close(self) -> None:
        return

    def _session_config(self) -> dict[str, Any]:
        return _session_config(self._settings)

    def transcribe(self, audio: np.ndarray, *, turn_index: int, final: bool) -> AsrResult:
        del turn_index, final
        if audio.size == 0:
            return AsrResult(text="")
        with self._lock:
            return asyncio.run(self._transcribe_once(audio))

    async def _transcribe_once(self, audio: np.ndarray) -> AsrResult:
        stream = LiveTranscribeStream(self._settings)
        try:
            await stream.begin_turn()
            await stream.append(audio)
            text = await stream.commit()
            return AsrResult(text=text)
        finally:
            await stream.close()
