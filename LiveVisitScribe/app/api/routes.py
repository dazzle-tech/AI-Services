"""WS /api/v1/live, GET /api/v1/health, GET /api/v1/ready and GET /api/v1/metrics.

The receive loop only reads frames and puts them on a queue; one worker per socket processes them in
order, so a slow speech pass never stops the socket from reading. When the worker is more than
MAX_BACKLOG_SECONDS behind real time, partial lines are skipped (final lines never are). Past
MAX_BACKLOG_HARD_SECONDS the visit is closed.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ValidationError

from app.core import metrics
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


def _picked_up_mode() -> str:
    if settings.use_llm_stub:
        return "stub"
    return "model" if model_client.is_configured() else "unconfigured"


@router.get("/api/v1/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    transcriber = getattr(request.app.state, "transcriber", None)
    asr = getattr(transcriber, "name", "unavailable") if transcriber is not None else "unavailable"
    return HealthResponse(status="ok" if transcriber is not None else "degraded", asr=asr, picked_up=_picked_up_mode())


@router.get("/api/v1/ready")
async def ready(request: Request) -> JSONResponse:
    """Readiness. Liveness stays on /health, which does not look at capacity or the model."""
    transcriber = getattr(request.app.state, "transcriber", None)
    problems: list[str] = []
    if transcriber is None:
        problems.append("speech model is not loaded")
    if not model_client.is_configured():
        problems.append("picked-up model is not configured")
    active = int(metrics.sessions_active.value)
    full = active >= settings.max_sessions
    if full:
        problems.append("at session capacity")
    body = {
        "ready": not problems,
        "problems": problems,
        "sessions_active": active,
        "sessions_max": settings.max_sessions,
        "full": full,
    }
    return JSONResponse(body, status_code=200 if not problems else 503)


@router.get("/api/v1/metrics")
async def metrics_text() -> Response:
    return Response(content=metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")


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
                allow_partial = backlog.seconds <= settings.max_backlog_seconds
                skipped = await session.feed(payload, allow_partial=allow_partial)
                if skipped:
                    metrics.partials_skipped_total.inc(skipped)
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


def _audio_seconds(nbytes: int, sample_rate: int, channels: int) -> float:
    per_second = 2 * channels * sample_rate
    return nbytes / per_second if per_second else 0.0


@router.websocket("/api/v1/live")
async def live(ws: WebSocket) -> None:
    await ws.accept()
    session_id = secrets.token_hex(4)
    emit = _Emitter(ws)
    reason = "client_disconnect"
    close_code = 1000
    acquired = False
    started_at: float | None = None
    audio_bytes = 0
    sample_rate = 16000
    channels = 1
    warned_length = False
    route_paused = False
    session: LiveSession | None = None
    worker: asyncio.Task | None = None
    queue: asyncio.Queue = asyncio.Queue()
    backlog = _Backlog(sample_rate, channels)
    stop_requested = False
    disconnected = False
    logger.info("session %s started", session_id)

    try:
        transcriber = getattr(ws.app.state, "transcriber", None)
        if transcriber is None:
            await emit({"type": "error", "detail": "Speech model is not loaded."})
            close_code = 1011
            reason = "client_disconnect"
            return

        while True:
            if session is None:
                timeout = settings.start_timeout_seconds
            elif route_paused:
                timeout = settings.pause_timeout_seconds
            else:
                timeout = settings.idle_timeout_seconds
            try:
                message = await asyncio.wait_for(ws.receive(), timeout)
            except asyncio.TimeoutError:
                if session is None:
                    await emit({"type": "error", "detail": "Send 'start' before the session times out."})
                    reason = "start_timeout"
                    break
                if route_paused:
                    await emit({"type": "error", "detail": "Paused too long; ending the session."})
                    reason = "pause_timeout"
                    break
                await emit({"type": "warning", "detail": "No audio received; ending the session."})
                await queue.put(("stop", None))
                stop_requested = True
                reason = "idle_timeout"
                break
            if message["type"] == "websocket.disconnect":
                disconnected = True
                break

            text, data = message.get("text"), message.get("bytes")
            if data is not None:
                if len(data) > settings.max_frame_bytes:
                    await emit({"type": "error", "detail": "Audio frame too large for this server."})
                    close_code = 1009
                    reason = "frame_too_large"
                    break
                if session is None:
                    await emit({"type": "error", "detail": "Send 'start' before audio."})
                    continue
                if route_paused:
                    continue
                backlog.add(len(data))
                if backlog.seconds > settings.max_backlog_hard_seconds:
                    metrics.sessions_overloaded_total.inc()
                    await emit({"type": "error", "detail": "busy: this visit is behind real time."})
                    close_code = 1013
                    reason = "overloaded"
                    break
                audio_bytes += len(data)
                await queue.put(("audio", data))
                heard = _audio_seconds(audio_bytes, sample_rate, channels)
                if heard >= settings.session_warn_seconds and not warned_length:
                    warned_length = True
                    await emit({"type": "warning", "detail": "session_length", "seconds": round(heard, 1)})
                if heard >= settings.max_session_seconds:
                    await emit({"type": "warning", "detail": "session_length", "seconds": round(heard, 1)})
                    await queue.put(("stop", None))
                    stop_requested = True
                    reason = "max_length"
                    break
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
                if not metrics.try_acquire_session():
                    await emit({"type": "error", "detail": "busy: too many live visits on this server."})
                    close_code = 1013
                    reason = "busy"
                    break
                acquired = True
                started_at = time.monotonic()
                sample_rate = start.sample_rate
                channels = start.channels
                session = LiveSession(
                    transcriber=transcriber,
                    emit=emit,
                    settings=settings,
                    sample_rate=start.sample_rate,
                    channels=start.channels,
                    patient_context=start.patient_context,
                    session_id=session_id,
                )
                backlog = _Backlog(start.sample_rate, start.channels)
                worker = asyncio.create_task(_work(session, queue, backlog, emit))
                await emit({"type": "ready", "sample_rate": start.sample_rate, "channels": start.channels})
            elif kind in ("pause", "resume", "stop"):
                if session is None:
                    await emit({"type": "error", "detail": f"Send 'start' before '{kind}'."})
                    continue
                if kind == "pause":
                    route_paused = True
                elif kind == "resume":
                    await queue.put((kind, None))
                    route_paused = False
                    continue
                await queue.put((kind, None))
                if kind == "stop":
                    stop_requested = True
                    reason = "stop"
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
        line_count = len(session.final_segments) if session is not None else 0
        if acquired and started_at is not None:
            metrics.session_duration.observe(time.monotonic() - started_at)
            metrics.release_session()
        logger.info(
            "session %s ended reason=%s audio_s=%.1f lines=%d",
            session_id,
            reason,
            _audio_seconds(audio_bytes, sample_rate, channels),
            line_count,
        )
        if not disconnected:
            try:
                await ws.close(code=close_code)
            except Exception:
                pass
