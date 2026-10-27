"""Speech-to-text backends for the live transcript."""

from __future__ import annotations

from typing import Optional

from app.asr.base import AsrResult, Transcriber
from app.core.config import Settings
from app.core.logging import get_logger

__all__ = ["AsrResult", "Transcriber", "build_transcriber"]

logger = get_logger(__name__)


def build_transcriber(settings: Settings) -> Optional[Transcriber]:
    """Stub when USE_LLM_STUB=true; otherwise OpenAI gpt-live-transcribe. None if it cannot start."""
    if settings.use_llm_stub:
        from app.asr.stub import StubTranscriber

        return StubTranscriber()
    try:
        from app.asr.live_transcribe import LiveTranscribeTranscriber

        return LiveTranscribeTranscriber(settings)
    except Exception:
        logger.exception("Could not start gpt-live-transcribe; the live socket will report an error")
        return None
