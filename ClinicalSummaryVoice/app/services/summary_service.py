"""Transcribe one speaker, then summarize the dictation."""

from __future__ import annotations

import io
import json
from pathlib import Path

from fastapi import HTTPException, status
from openai import OpenAI

from app.ai.prompts import SUMMARY_SYSTEM_PROMPT, TRANSCRIBE_PROMPT, build_user_prompt
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def summarize_dictation(*, audio_bytes: bytes, filename: str) -> dict:
    if settings.use_llm_stub:
        transcript = "Stub dictation. Patient reports headache for three days. Follow up in two weeks."
        summary = _stub_summary(transcript)
    else:
        transcript = transcribe_audio(audio_bytes, filename)
        if not transcript:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No speech was detected in the audio",
            )
        summary = summarize_transcript(transcript)
    return {**summary, "transcript": transcript}


def transcribe_audio(audio_bytes: bytes, filename: str) -> str:
    client = _openai_client()
    suffix = Path(filename).suffix.lower() or ".wav"
    safe_name = Path(filename).name or f"audio{suffix}"
    buffer = io.BytesIO(audio_bytes)
    buffer.name = safe_name
    try:
        result = client.audio.transcriptions.create(
            model=settings.openai_transcribe_model,
            file=buffer,
            prompt=TRANSCRIBE_PROMPT,
            response_format="json",
        )
    except Exception as exc:
        logger.exception("Transcription failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Transcription failed: {exc.__class__.__name__}",
        ) from exc
    return (getattr(result, "text", None) or "").strip()


def summarize_transcript(transcript: str) -> dict:
    client = _openai_client()
    try:
        response = client.chat.completions.create(
            model=settings.openai_summary_model,
            temperature=settings.openai_temperature,
            timeout=settings.openai_timeout,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(transcript)},
            ],
        )
    except Exception as exc:
        logger.exception("Summary failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Summary failed: {exc.__class__.__name__}",
        ) from exc

    content = response.choices[0].message.content or ""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Summary model did not return JSON",
        ) from exc
    if not isinstance(payload, dict) or not str(payload.get("summary") or "").strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Summary model did not return a summary",
        )
    return {"summary": str(payload["summary"]).strip()}


def _openai_client() -> OpenAI:
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY is not set",
        )
    return OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        timeout=settings.openai_timeout,
        max_retries=settings.openai_max_retries,
    )


def _stub_summary(transcript: str) -> dict:
    return {
        "summary": (
            "Patient reports a headache for three days. "
            "Assessment: Headache. Plan: Follow up in two weeks."
        )
    }
