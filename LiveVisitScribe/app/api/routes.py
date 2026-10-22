"""WS /api/v1/live and GET /api/v1/health.

The receive loop only reads frames and puts them on a queue; one worker per socket processes them in
order, so a slow speech pass never stops the socket from reading. When the worker is more than
MAX_BACKLOG_SECONDS behind real time, partial lines are skipped (final lines never are).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.logging import get_logger
from app.live import model_client
from app.live.session import LiveSession
from app.models.schemas import StartMessage

logger = get_logger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    asr: str
    picked_up: str


@router.get("/api/v1/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    transcriber = getattr(request.app.state, "transcriber", None)
    asr = getattr(transcriber, "name", "unavailable") if transcriber is not None else "unavailable"
    if settings.use_llm_stub:
        picked_up = "stub"
    else:
        picked_up = "model" if model_client.is_configured() else "unconfigured"
    return HealthResponse(status="ok" if transcriber is not None else "degraded", asr=asr, picked_up=picked_up)


class _Emitter:
    """Sends JSON to the socket. Two tasks can send, so sends are serialized; a closed socket is ignored."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws
        self._lock = asyncio.Lock()
        self.closed = False

    async def __call__(self, message: dict[str, Any]) -> None:
        if self.closed:
            return
        async with self._lock:
            try:
                await self._ws.send_text(json.dumps(message, ensure_ascii=False))
            except Exception:
                self.closed = True


class _Backlog:
    def __init__(self, sample_rate: int, channels: int) -> None:
        self._bytes_per_second = 2 * channels * sample_rate
        self._bytes = 0

    def add(self, size: int) -> None:
        self._bytes += size

    def remove(self, size: int) -> None:
        self._bytes = max(0, self._bytes - size)

    @property
    def seconds(self) -> float:
        return self._bytes / self._bytes_per_second


async def _work(session: LiveSession, queue: asyncio.Queue, backlog: _Backlog, emit: _Emitter) -> None:
    error_sent = False
    while True:
        kind, payload = await queue.get()
        try:
            if kind == "audio":
                backlog.remove(len(payload))
                await session.feed(payload, allow_partial=backlog.seconds <= settings.max_backlog_seconds)
            elif kind == "pause":
                await session.pause()
                await emit({"type": "paused"})
            elif kind == "resume":
                await session.resume()
                await emit({"type": "resumed"})
            elif kind == "stop":
                await session.stop()
                return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Live processing failed (%s)", kind)
            if not error_sent:
                error_sent = True
                await emit({"type": "error", "detail": "Transcription failed for part of the audio"})
            if kind == "stop":
                return


def _describe(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors())


@router.websocket("/api/v1/live")
async def live(ws: WebSocket) -> None:
    await ws.accept()
    emit = _Emitter(ws)
    transcriber = getattr(ws.app.state, "transcriber", None)
    if transcriber is None:
        await emit({"type": "error", "detail": "Speech model is not loaded."})
        await ws.close(code=1011)
        return

    session: LiveSession | None = None
    worker: asyncio.Task | None = None
    queue: asyncio.Queue = asyncio.Queue()
    backlog = _Backlog(16000, 1)
    stop_requested = False
    disconnected = False

    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                disconnected = True
                break

            text, data = message.get("text"), message.get("bytes")
            if data is not None:
                if session is None:
                    await emit({"type": "error", "detail": "Send 'start' before audio."})
                    continue
                backlog.add(len(data))
                await queue.put(("audio", data))
                continue
            if text is None:
                continue

            try:
                control = json.loads(text)
                kind = str(control.get("type") or "").lower() if isinstance(control, dict) else ""
            except json.JSONDecodeError:
                await emit({"type": "error", "detail": "Invalid JSON control message."})
                continue

            if kind == "start":
                if session is not None:
                    await emit({"type": "error", "detail": "Already started."})
                    continue
                try:
                    start = StartMessage.model_validate({**control, "type": "start"})
                except ValidationError as exc:
                    await emit({"type": "error", "detail": f"Invalid start message: {_describe(exc)}"})
                    continue
                session = LiveSession(
                    transcriber=transcriber,
                    emit=emit,
                    settings=settings,
                    sample_rate=start.sample_rate,
                    channels=start.channels,
                    patient_context=start.patient_context,
                )
                backlog = _Backlog(start.sample_rate, start.channels)
                worker = asyncio.create_task(_work(session, queue, backlog, emit))
                await emit({"type": "ready", "sample_rate": start.sample_rate, "channels": start.channels})
            elif kind in ("pause", "resume", "stop"):
                if session is None:
                    await emit({"type": "error", "detail": f"Send 'start' before '{kind}'."})
                    continue
                await queue.put((kind, None))
                if kind == "stop":
                    stop_requested = True
                    break
            else:
                await emit({"type": "error", "detail": f"Unknown control type: {kind or 'missing'}"})
    except WebSocketDisconnect:
        disconnected = True
    finally:
        if worker is not None:
            if stop_requested and not disconnected:
                await worker
            else:
                worker.cancel()
                try:
                    await worker
                except asyncio.CancelledError:
                    pass
        if session is not None and not (stop_requested and not disconnected):
            await session.abort()
        if not disconnected:
            try:
                await ws.close()
            except Exception:
                pass
