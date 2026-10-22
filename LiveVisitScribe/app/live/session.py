"""One live visit: audio frames in, transcript lines and the picked-up list out.

The session holds only the audio of the line being spoken (a few seconds) and the finished text
lines. Nothing is written anywhere, and the audio of a finished line is dropped.

Lines: speech starts a line; while it continues a partial (final=false) is refreshed every
STREAM_CHUNK_SECONDS by transcribing the line so far; SILENCE_MS of silence ends it (final=true).
A line that runs past MAX_TURN_SECONDS is split, and STREAM_OVERLAP_SECONDS of audio is carried into
the next line so a word on the cut is not lost.

Time: start_ms / end_ms count the audio received while not paused, so they match a recording whose
recorder is also paused.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Optional

import numpy as np

from app.asr.base import Transcriber
from app.audio.pcm import TARGET_SR, pcm_to_float32
from app.core.config import Settings
from app.core.logging import get_logger
from app.live import picked_up
from app.live.speaker import guess_speaker
from app.live.text_utils import detect_lang
from app.models.schemas import PatientContext, Segment

logger = get_logger(__name__)

Emit = Callable[[dict], Awaitable[None]]

FRAME_SAMPLES = TARGET_SR // 50  # 20 ms
_PRE_ROLL_FRAMES = 15  # 300 ms kept before speech starts so the first word is not clipped
_TAIL_KEEP_SAMPLES = int(0.2 * TARGET_SR)  # silence kept after the last word when a line is transcribed


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
        self.id: Optional[str] = None
        self.last_text = ""

    def add(self, frame: np.ndarray, speech: bool) -> None:
        self.frames.append(frame)
        self.samples += frame.size
        self.since_partial += frame.size
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
    ) -> None:
        self._asr = transcriber
        self._emit = emit
        self._settings = settings
        self._sample_rate = sample_rate
        self._channels = channels
        self._context = patient_context

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

    # --- public ---------------------------------------------------------

    @property
    def final_segments(self) -> list[Segment]:
        return list(self._finals)

    async def feed(self, data: bytes, *, allow_partial: bool = True) -> None:
        if self._paused or self._stopped or not data:
            return
        audio = self._decode(data)
        if audio.size == 0:
            return
        pending = np.concatenate([self._pending, audio]) if self._pending.size else audio
        usable = (pending.size // FRAME_SAMPLES) * FRAME_SAMPLES
        self._pending = pending[usable:].copy()
        for frame in pending[:usable].reshape(-1, FRAME_SAMPLES):
            await self._on_frame(frame, allow_partial)

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
        """Close the open line, flush the picked-up list, and send `final`."""
        if self._stopped:
            return
        self._stopped = True
        try:
            await self._finalize_turn()
        except Exception:
            logger.exception("Could not finish the last line")
        await self._cancel_extract_task()
        if self._dirty:
            await self._run_extract()
        await self._emit(
            {
                "type": "final",
                "segments": [segment.model_dump() for segment in self._finals],
                "audio_ms": _ms(self._position),
            }
        )

    async def abort(self) -> None:
        """The socket closed without a stop: drop everything, send nothing."""
        self._stopped = True
        await self._cancel_extract_task()

    # --- audio to lines -------------------------------------------------

    def _decode(self, data: bytes) -> np.ndarray:
        data = self._byte_carry + data
        whole = len(data) - (len(data) % (2 * self._channels))
        self._byte_carry = data[whole:]
        return pcm_to_float32(data[:whole], self._sample_rate, self._channels)

    async def _on_frame(self, frame: np.ndarray, allow_partial: bool) -> None:
        cfg = self._settings
        speech = float(np.sqrt(np.mean(frame * frame))) >= cfg.silence_rms
        self._position += frame.size

        turn = self._turn
        if turn is None:
            if not speech:
                self._pre_roll.append(frame)
                del self._pre_roll[:-_PRE_ROLL_FRAMES]
                return
            lead = self._pre_roll
            self._pre_roll = []
            start = self._position - frame.size - sum(item.size for item in lead)
            turn = self._turn = _Turn(start, [*lead, frame])
            turn.speech_samples = frame.size
            return

        turn.add(frame, speech)
        silence_samples = cfg.silence_ms * TARGET_SR // 1000
        if turn.trailing_silence >= silence_samples:
            await self._finalize_turn()
        elif turn.samples >= int(cfg.max_turn_seconds * TARGET_SR):
            await self._finalize_turn(carry_overlap=True)
        elif (
            allow_partial
            and turn.since_partial >= int(cfg.stream_chunk_seconds * TARGET_SR)
            and turn.speech_samples >= cfg.min_speech_ms * TARGET_SR // 1000
        ):
            await self._partial(turn)

    async def _partial(self, turn: _Turn) -> None:
        turn.since_partial = 0
        result = await asyncio.to_thread(
            self._asr.transcribe, turn.audio(), turn_index=len(self._finals), final=False
        )
        text = " ".join(result.text.split())
        if not text or text == turn.last_text:
            return
        turn.last_text = text
        await self._emit_segment(turn, text, final=False, end_sample=turn.start + turn.samples)

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
            result = await asyncio.to_thread(
                self._asr.transcribe,
                turn.audio(trim_silence=True),
                turn_index=len(self._finals),
                final=True,
            )
            text = " ".join(result.text.split()) or turn.last_text
            if text:
                end = turn.start + turn.samples - turn.trailing_silence
                await self._emit_segment(turn, text, final=True, end_sample=end)
                self._dirty = True
                self._schedule_extract()

        if carry is not None:
            start = self._position - carry.size
            self._turn = _Turn(start, [carry], speech_samples=0)

    async def _emit_segment(self, turn: _Turn, text: str, *, final: bool, end_sample: int) -> None:
        if turn.id is None:
            turn.id = f"t{self._next_id}"
            self._next_id += 1
        segment = Segment(
            id=turn.id,
            speaker=guess_speaker(text),
            start_ms=_ms(turn.start),
            end_ms=_ms(max(end_sample, turn.start)),
            text=text,
            lang=detect_lang(text),
            final=final,
        )
        if final:
            self._finals.append(segment)
        await self._emit({"type": "segment", **segment.model_dump()})

    # --- picked up so far -----------------------------------------------

    def _schedule_extract(self) -> None:
        if self._extract_task is None or self._extract_task.done():
            self._extract_task = asyncio.create_task(self._extract_loop())

    async def _extract_loop(self) -> None:
        interval = self._settings.picked_up_interval_seconds
        while self._dirty and not self._stopped:
            wait = self._last_extract + interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            if not self._dirty or self._stopped:
                break
            await self._run_extract()

    async def _run_extract(self) -> None:
        self._dirty = False
        self._last_extract = time.monotonic()
        try:
            picked = await picked_up.extract(self.final_segments, self._context)
        except asyncio.CancelledError:
            self._dirty = True
            raise
        except Exception as exc:
            logger.warning("Picked-up update failed: %s", exc.__class__.__name__)
            if not self._extract_error_sent:
                self._extract_error_sent = True
                await self._emit({"type": "error", "detail": "Picked up so far could not be updated"})
            return
        payload = picked.model_dump()
        if payload == self._last_picked or (self._last_picked is None and picked.is_empty()):
            return
        self._last_picked = payload
        await self._emit({"type": "picked_up", **payload})

    async def _cancel_extract_task(self) -> None:
        task = self._extract_task
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._extract_task = None
