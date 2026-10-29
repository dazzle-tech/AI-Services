"""One live visit: audio frames in, transcript lines and the picked-up list out.

The session holds only the audio of the line being spoken (a few seconds) and the finished text
lines. Nothing is written anywhere, and the audio of a finished line is dropped.

With gpt-live-transcribe, audio is streamed to OpenAI as it arrives and partial text is sent
letter by letter. Local silence still ends a line (final=true). The stub backend still refreshes
a partial every STREAM_CHUNK_SECONDS by re-reading the line so far.

Time: start_ms / end_ms count the audio received while not paused, so they match a recording whose
recorder is also paused.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Optional

import numpy as np

from app.asr.base import AsrResult, Transcriber
from app.audio.pcm import TARGET_SR, pcm_to_float32
from app.core import metrics
from app.core.config import Settings
from app.core.logging import get_logger
from app.live import picked_up
from app.live.speaker import guess_speaker
from app.live.text_utils import detect_lang
from app.models.schemas import PatientContext, PickedUp, Segment

logger = get_logger(__name__)

Emit = Callable[[dict], Awaitable[None]]

FRAME_SAMPLES = TARGET_SR // 50  # 20 ms
_PRE_ROLL_FRAMES = 15  # 300 ms kept before speech starts so the first word is not clipped
_TAIL_KEEP_SAMPLES = int(0.2 * TARGET_SR)  # silence kept after the last word when a line is transcribed
_STREAM_FLUSH_SAMPLES = TARGET_SR // 10  # ~100 ms of audio between Realtime appends


def _ms(samples: int) -> int:
    return int(samples * 1000 / TARGET_SR)


class _Turn:
    def __init__(self, start: int, frames: list[np.ndarray], speech_samples: int = 0) -> None:
        self.start = start
        self.frames = frames
        self.samples = sum(frame.size for frame in frames)
        self.speech_samples = speech_samples
        self.trailing_silence = 0
        self.since_partial = 0
        self.since_stream = 0
        self.id: Optional[str] = None
        self.last_text = ""
        self.stream_started = False

    def add(self, frame: np.ndarray, speech: bool) -> None:
        self.frames.append(frame)
        self.samples += frame.size
        self.since_partial += frame.size
        self.since_stream += frame.size
        if speech:
            self.speech_samples += frame.size
            self.trailing_silence = 0
        else:
            self.trailing_silence += frame.size

    def audio(self, *, trim_silence: bool = False) -> np.ndarray:
        audio = np.concatenate(self.frames) if self.frames else np.zeros(0, dtype=np.float32)
        if trim_silence and self.trailing_silence > _TAIL_KEEP_SAMPLES:
            audio = audio[: audio.size - (self.trailing_silence - _TAIL_KEEP_SAMPLES)]
        return audio


class LiveSession:
    def __init__(
        self,
        *,
        transcriber: Transcriber,
        emit: Emit,
        settings: Settings,
        sample_rate: int = TARGET_SR,
        channels: int = 1,
        patient_context: Optional[PatientContext] = None,
        session_id: str = "",
    ) -> None:
        self._asr = transcriber
        self._emit = emit
        self._settings = settings
        self._sample_rate = sample_rate
        self._channels = channels
        self._context = patient_context
        self._session_id = session_id

        self._byte_carry = b""
        self._pending = np.zeros(0, dtype=np.float32)
        self._pre_roll: list[np.ndarray] = []
        self._turn: Optional[_Turn] = None
        self._position = 0  # samples (16 kHz) processed while not paused
        self._paused = False
        self._stopped = False

        self._finals: list[Segment] = []
        self._next_id = 1

        self._dirty = False
        self._last_extract = float("-inf")
        self._last_picked: Optional[dict] = None
        self._extract_task: Optional[asyncio.Task] = None
        self._extract_error_sent = False

        self._stream: Any = None
        self._stream_sent = 0
        self._use_live_stream = callable(getattr(transcriber, "open_stream", None))

    # --- public ---------------------------------------------------------

    @property
    def final_segments(self) -> list[Segment]:
        return list(self._finals)

    async def feed(self, data: bytes, *, allow_partial: bool = True) -> int:
        """Ingest PCM. Returns how many partials were skipped because the socket is behind."""
        if self._paused or self._stopped or not data:
            return 0
        audio = self._decode(data)
        if audio.size == 0:
            return 0
        pending = np.concatenate([self._pending, audio]) if self._pending.size else audio
        usable = (pending.size // FRAME_SAMPLES) * FRAME_SAMPLES
        self._pending = pending[usable:].copy()
        skipped = 0
        for frame in pending[:usable].reshape(-1, FRAME_SAMPLES):
            skipped += await self._on_frame(frame, allow_partial)
        return skipped

    async def pause(self) -> None:
        """Close the open line, then ignore audio until resume."""
        if self._paused:
            return
        await self._finalize_turn()
        self._paused = True
        self._pending = np.zeros(0, dtype=np.float32)
        self._pre_roll = []
        self._byte_carry = b""

    async def resume(self) -> None:
        self._paused = False

    async def stop(self) -> None:
        """Close the open line, flush picked_up, then send `final` with transcript + picked_up together."""
        if self._stopped:
            return
        self._stopped = True
        try:
            await self._finalize_turn()
        except Exception:
            logger.exception("Could not finish the last line")
        await self._close_stream()
        await self._cancel_extract_task()
        # Always rebuild (or fall back) so final never ships without a full picked_up object.
        if self._finals:
            self._dirty = True
            try:
                await asyncio.wait_for(
                    self._run_extract(),
                    self._settings.stop_flush_timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning("session %s picked-up flush timed out", self._session_id or "-")
                await self._emit_picked_up_fallback()
            except Exception:
                logger.exception("session %s picked-up flush failed", self._session_id or "-")
                await self._emit_picked_up_fallback()
        else:
            await self._emit_picked_up_fallback()

        payload = self._picked_up_payload()
        # Standalone message for live UIs that listen for type=picked_up during the visit.
        await self._emit({"type": "picked_up", **payload})
        # Full visit result: transcript + scratch list in one message (integrators often only read final).
        await self._emit(
            {
                "type": "final",
                "segments": [segment.model_dump() for segment in self._finals],
                "audio_ms": _ms(self._position),
                "picked_up": payload,
            }
        )
        logger.info(
            "session %s final lines=%d picked_up_empty=%s keys=%s",
            self._session_id or "-",
            len(self._finals),
            PickedUp.model_validate(payload).is_empty(),
            sorted(payload.keys()),
        )

    async def abort(self) -> None:
        """The socket closed without a stop: drop everything, send nothing."""
        self._stopped = True
        await self._close_stream()
        await self._cancel_extract_task()

    # --- audio to lines -------------------------------------------------

    def _decode(self, data: bytes) -> np.ndarray:
        data = self._byte_carry + data
        whole = len(data) - (len(data) % (2 * self._channels))
        self._byte_carry = data[whole:]
        return pcm_to_float32(data[:whole], self._sample_rate, self._channels)

    async def _on_frame(self, frame: np.ndarray, allow_partial: bool) -> int:
        cfg = self._settings
        speech = float(np.sqrt(np.mean(frame * frame))) >= cfg.silence_rms
        self._position += frame.size

        turn = self._turn
        if turn is None:
            if not speech:
                self._pre_roll.append(frame)
                del self._pre_roll[:-_PRE_ROLL_FRAMES]
                return 0
            lead = self._pre_roll
            self._pre_roll = []
            start = self._position - frame.size - sum(item.size for item in lead)
            turn = self._turn = _Turn(start, [*lead, frame])
            turn.speech_samples = frame.size
            if self._use_live_stream:
                await self._stream_begin(turn)
            return 0

        turn.add(frame, speech)
        silence_samples = cfg.silence_ms * TARGET_SR // 1000
        if turn.trailing_silence >= silence_samples:
            await self._finalize_turn()
        elif turn.samples >= int(cfg.max_turn_seconds * TARGET_SR):
            await self._finalize_turn(carry_overlap=True)
        elif self._use_live_stream:
            if not allow_partial:
                return 0
            await self._stream_continue(turn)
        elif (
            turn.since_partial >= int(cfg.stream_chunk_seconds * TARGET_SR)
            and turn.speech_samples >= cfg.min_speech_ms * TARGET_SR // 1000
        ):
            if not allow_partial:
                turn.since_partial = 0
                return 1
            await self._partial(turn)
        return 0

    async def _ensure_stream(self) -> Any:
        if self._stream is not None:
            return self._stream
        opener = getattr(self._asr, "open_stream", None)
        if not callable(opener):
            return None
        stream = opener()
        await stream.connect()
        self._stream = stream
        return stream

    async def _close_stream(self) -> None:
        stream = self._stream
        self._stream = None
        self._stream_sent = 0
        if stream is None:
            return
        try:
            await stream.close()
        except Exception:
            logger.exception("session %s could not close the speech stream", self._session_id or "-")

    async def _stream_begin(self, turn: _Turn) -> None:
        stream = await self._ensure_stream()
        if stream is None:
            return
        await stream.begin_turn()
        turn.stream_started = True
        audio = turn.audio()
        self._stream_sent = audio.size
        turn.since_stream = 0
        started = time.perf_counter()
        text = await stream.append(audio)
        metrics.observe_asr(final=False, elapsed=time.perf_counter() - started, audio_seconds=audio.size / TARGET_SR)
        await self._emit_partial_text(turn, text, end_sample=turn.start + turn.samples)

    async def _stream_continue(self, turn: _Turn) -> None:
        if not turn.stream_started or turn.since_stream < _STREAM_FLUSH_SAMPLES:
            return
        stream = await self._ensure_stream()
        if stream is None:
            return
        audio = turn.audio()
        chunk = audio[self._stream_sent :]
        if chunk.size == 0:
            turn.since_stream = 0
            return
        self._stream_sent = audio.size
        turn.since_stream = 0
        started = time.perf_counter()
        text = await stream.append(chunk)
        metrics.observe_asr(final=False, elapsed=time.perf_counter() - started, audio_seconds=chunk.size / TARGET_SR)
        await self._emit_partial_text(turn, text, end_sample=turn.start + turn.samples)

    async def _transcribe(self, audio: np.ndarray, *, turn_index: int, final: bool) -> AsrResult:
        started = time.perf_counter()
        try:
            return await asyncio.to_thread(
                self._asr.transcribe, audio, turn_index=turn_index, final=final
            )
        finally:
            elapsed = time.perf_counter() - started
            audio_seconds = float(audio.size) / TARGET_SR if audio.size else 0.0
            metrics.observe_asr(final=final, elapsed=elapsed, audio_seconds=audio_seconds)

    async def _partial(self, turn: _Turn) -> None:
        turn.since_partial = 0
        result = await self._transcribe(turn.audio(), turn_index=len(self._finals), final=False)
        text = " ".join(result.text.split())
        if not text or text == turn.last_text:
            return
        turn.last_text = text
        await self._emit_segment(
            turn, text, final=False, end_sample=turn.start + turn.samples, low_confidence=result.low_confidence
        )

    async def _finalize_turn(self, *, carry_overlap: bool = False) -> None:
        turn = self._turn
        if turn is None:
            return
        self._turn = None
        self._pre_roll = []

        carry: Optional[np.ndarray] = None
        if carry_overlap:
            overlap = int(self._settings.stream_overlap_seconds * TARGET_SR)
            audio = turn.audio()
            if overlap > 0 and audio.size > overlap:
                carry = audio[-overlap:].copy()

        if turn.speech_samples >= self._settings.min_speech_ms * TARGET_SR // 1000:
            if self._use_live_stream and turn.stream_started:
                await self._finalize_stream_turn(turn)
            else:
                result = await self._transcribe(
                    turn.audio(trim_silence=True),
                    turn_index=len(self._finals),
                    final=True,
                )
                text = " ".join(result.text.split()) or turn.last_text
                if text:
                    end = turn.start + turn.samples - turn.trailing_silence
                    await self._emit_segment(
                        turn, text, final=True, end_sample=end, low_confidence=result.low_confidence
                    )
                    self._dirty = True
                    self._schedule_extract()

        self._stream_sent = 0
        if carry is not None:
            start = self._position - carry.size
            nxt = self._turn = _Turn(start, [carry], speech_samples=0)
            if self._use_live_stream:
                await self._stream_begin(nxt)

    async def _finalize_stream_turn(self, turn: _Turn) -> None:
        stream = await self._ensure_stream()
        if stream is None:
            return
        audio = turn.audio(trim_silence=True)
        leftover = audio[self._stream_sent :]
        started = time.perf_counter()
        if leftover.size:
            await stream.append(leftover)
        text = await stream.commit()
        metrics.observe_asr(
            final=True,
            elapsed=time.perf_counter() - started,
            audio_seconds=max(audio.size, 1) / TARGET_SR,
        )
        text = " ".join(text.split()) or turn.last_text
        if not text:
            return
        end = turn.start + turn.samples - turn.trailing_silence
        turn.last_text = text
        await self._emit_segment(turn, text, final=True, end_sample=end, low_confidence=[])
        self._dirty = True
        self._schedule_extract()

    async def _emit_partial_text(self, turn: _Turn, text: str, *, end_sample: int) -> None:
        """Send each real model update once. Do not invent a letter-by-letter delay."""
        text = " ".join((text or "").split())
        if not text or text == turn.last_text:
            return
        turn.last_text = text
        await self._emit_segment(turn, text, final=False, end_sample=end_sample, low_confidence=[])

    async def _emit_segment(
        self,
        turn: _Turn,
        text: str,
        *,
        final: bool,
        end_sample: int,
        low_confidence: list[str],
    ) -> None:
        if turn.id is None:
            turn.id = f"t{self._next_id}"
            self._next_id += 1
        speaker = guess_speaker(text)
        segment = Segment(
            id=turn.id,
            speaker=speaker if speaker in ("doctor", "patient") else "patient",
            start_ms=_ms(turn.start),
            end_ms=_ms(max(end_sample, turn.start)),
            text=text,
            lang=detect_lang(text),
            final=final,
            low_confidence_numbers=list(low_confidence),
        )
        if final:
            self._finals.append(segment)
        await self._emit({"type": "segment", **segment.model_dump()})

    # --- picked up so far -----------------------------------------------

    def _schedule_extract(self) -> None:
        if self._extract_task is None or self._extract_task.done():
            self._extract_task = asyncio.create_task(self._extract_loop())

    async def _extract_loop(self) -> None:
        # Display-only: no interval, no “unchanged” skip. Every new final triggers a send.
        while self._dirty and not self._stopped:
            await self._run_extract()

    async def _run_extract(self) -> None:
        self._dirty = False
        self._last_extract = time.monotonic()
        started = time.perf_counter()
        try:
            picked, speakers = await picked_up.extract(self.final_segments, self._context)
        except asyncio.CancelledError:
            self._dirty = True
            raise
        except Exception as exc:
            metrics.extract.observe(time.perf_counter() - started)
            metrics.extract_failures_total.inc()
            logger.warning("session %s picked-up update failed: %s", self._session_id or "-", exc)
            if not self._extract_error_sent:
                self._extract_error_sent = True
                await self._emit({"type": "error", "detail": "Picked up so far could not be updated"})
            # Still send something to show (last list or empty) — never silent.
            await self._emit_picked_up_fallback()
            return
        metrics.extract.observe(time.perf_counter() - started)
        await self._apply_speakers(speakers)
        payload = picked.model_dump()
        self._last_picked = payload
        await self._emit({"type": "picked_up", **payload})

    def _picked_up_payload(self) -> dict[str, Any]:
        """Full picked_up body for the client (never omit keys)."""
        if self._last_picked is not None:
            return self._last_picked
        # Empty visit / failed extract: still return the enforced empty structure (record statuses, etc.).
        return picked_up.enforce_picked_up({}, self.final_segments, self._context).model_dump()

    async def _emit_picked_up_fallback(self) -> None:
        """Last known list, or a full empty structure — always a picked_up message for the UI."""
        payload = self._picked_up_payload()
        self._last_picked = payload
        await self._emit({"type": "picked_up", **payload})

    async def _apply_speakers(self, speakers: dict[str, str]) -> None:
        """Replace the word guess with the model's speaker and send the line again under the same id."""
        changed: list[Segment] = []
        for index, segment in enumerate(self._finals):
            speaker = speakers.get(segment.id)
            if not speaker or speaker == segment.speaker:
                continue
            segment = segment.model_copy(update={"speaker": speaker})
            self._finals[index] = segment
            changed.append(segment)
        for segment in changed:
            await self._emit({"type": "segment", **segment.model_dump()})

    async def _cancel_extract_task(self) -> None:
        task = self._extract_task
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._extract_task = None
