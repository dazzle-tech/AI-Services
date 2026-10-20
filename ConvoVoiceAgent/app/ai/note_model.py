"""JSON completions from the ambient note model (AMBIENT_NOTE_MODEL)."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from fastapi import HTTPException, status
from openai import APIError, AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def ensure_configured() -> None:
    if settings.use_llm_stub or settings.openai_api_key:
        return
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Ambient note model is not configured: set OPENAI_API_KEY or USE_LLM_STUB=true",
    )


async def complete_json(*, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    ensure_configured()
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        timeout=settings.openai_timeout_seconds,
        max_retries=1,
    )
    started = time.perf_counter()
    try:
        response = await client.chat.completions.create(
            model=settings.ambient_note_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=settings.openai_temperature,
            response_format={"type": "json_object"},
        )
    except APIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ambient note model failed: {exc.__class__.__name__}",
        ) from exc
    finally:
        await client.close()

    logger.info(
        "Ambient note model completed",
        extra={
            "event_type": "ambient_note_model",
            "model": settings.ambient_note_model,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        },
    )
    content = response.choices[0].message.content or ""
    try:
        payload = _parse_json(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ambient note model returned invalid JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ambient note model returned a non-object body",
        )
    return payload


def _parse_json(text: str) -> Any:
    cleaned = text.strip()
    fence = _JSON_FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    return json.loads(cleaned)
