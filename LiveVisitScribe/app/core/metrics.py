"""In-process counters for one LiveVisitScribe process. Counts and timings only: no text, no audio."""

from __future__ import annotations

import threading

from app.core.config import settings

_lock = threading.Lock()


class _Counter:
    def __init__(self) -> None:
        self.value = 0

    def inc(self, n: int = 1) -> None:
        with _lock:
            self.value += n


class _Gauge:
    def __init__(self) -> None:
        self.value = 0.0

    def set(self, value: float) -> None:
        with _lock:
            self.value = value

    def inc(self, n: float = 1) -> None:
        with _lock:
            self.value += n


class _SumCount:
    def __init__(self) -> None:
        self.sum = 0.0
        self.count = 0

    def observe(self, seconds: float) -> None:
        with _lock:
            self.sum += seconds
            self.count += 1


sessions_active = _Gauge()
sessions_total = _Counter()
sessions_rejected_total = _Counter()
sessions_overloaded_total = _Counter()
partials_skipped_total = _Counter()
extract_failures_total = _Counter()

session_duration = _SumCount()
asr_partial = _SumCount()
asr_final = _SumCount()
extract = _SumCount()
asr_last_rtf = _Gauge()


def try_acquire_session() -> bool:
    """Take one visit slot. False when this process is already at MAX_SESSIONS."""
    with _lock:
        if sessions_active.value >= settings.max_sessions:
            sessions_rejected_total.value += 1
            return False
        sessions_active.value += 1
        sessions_total.value += 1
        return True


def release_session() -> None:
    with _lock:
        sessions_active.value = max(0.0, sessions_active.value - 1)


def observe_asr(*, final: bool, elapsed: float, audio_seconds: float) -> None:
    bucket = asr_final if final else asr_partial
    bucket.observe(elapsed)
    if audio_seconds > 0:
        asr_last_rtf.set(elapsed / audio_seconds)


def _line(name: str, value: float) -> str:
    rendered = str(int(value)) if value == int(value) else f"{value:.6f}".rstrip("0").rstrip(".")
    return f"livescribe_{name} {rendered}"


def render() -> str:
    """Prometheus text. Gauges, counters, and sum/count pairs. No labels that carry visit content."""
    with _lock:
        rows = [
            ("# TYPE livescribe_sessions_active gauge", _line("sessions_active", sessions_active.value)),
            ("# TYPE livescribe_sessions_total counter", _line("sessions_total", sessions_total.value)),
            ("# TYPE livescribe_sessions_rejected_total counter", _line("sessions_rejected_total", sessions_rejected_total.value)),
            ("# TYPE livescribe_sessions_overloaded_total counter", _line("sessions_overloaded_total", sessions_overloaded_total.value)),
            ("# TYPE livescribe_partials_skipped_total counter", _line("partials_skipped_total", partials_skipped_total.value)),
            ("# TYPE livescribe_extract_failures_total counter", _line("extract_failures_total", extract_failures_total.value)),
            ("# TYPE livescribe_session_duration_seconds summary", _line("session_duration_seconds_sum", session_duration.sum)),
            ("", _line("session_duration_seconds_count", session_duration.count)),
            ("# TYPE livescribe_asr_partial_seconds summary", _line("asr_partial_seconds_sum", asr_partial.sum)),
            ("", _line("asr_partial_seconds_count", asr_partial.count)),
            ("# TYPE livescribe_asr_final_seconds summary", _line("asr_final_seconds_sum", asr_final.sum)),
            ("", _line("asr_final_seconds_count", asr_final.count)),
            ("# TYPE livescribe_extract_seconds summary", _line("extract_seconds_sum", extract.sum)),
            ("", _line("extract_seconds_count", extract.count)),
            ("# TYPE livescribe_asr_last_rtf gauge", _line("asr_last_rtf", asr_last_rtf.value)),
        ]
    lines: list[str] = []
    for row in rows:
        lines.extend(part for part in row if part)
    return "\n".join(lines) + "\n"
