"""One small JSON completion for the picked-up list (LIVE_EXTRACT_MODEL, any OpenAI-compatible endpoint)."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional

from openai import APIError, AsyncOpenAI

from app.core.config import settings

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)

# One client and one semaphore per event loop, rebuilt when the connection settings change.
_loops: dict[int, tuple[AsyncOpenAI, asyncio.Semaphore, tuple]] = {}


class ExtractionError(RuntimeError):
    """The picked-up model is missing, failed, or returned something unusable."""


def is_configured() -> bool:
    return settings.use_llm_stub or bool(settings.openai_api_key)


def _connection_key() -> tuple:
    return (
        settings.openai_api_key,
        settings.openai_base_url,
        settings.openai_timeout_seconds,
        settings.openai_max_retries,
        settings.extract_max_concurrency,
    )


def _client_for_loop() -> tuple[AsyncOpenAI, asyncio.Semaphore]:
    loop_id = id(asyncio.get_running_loop())
    key = _connection_key()
    current: Optional[tuple[AsyncOpenAI, asyncio.Semaphore, tuple]] = _loops.get(loop_id)
    if current is not None and current[2] == key:
        return current[0], current[1]
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    semaphore = asyncio.Semaphore(max(1, settings.extract_max_concurrency))
    _loops[loop_id] = (client, semaphore, key)
    return client, semaphore


async def complete_json(*, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    if not settings.openai_api_key:
        raise ExtractionError("Picked-up model is not configured: set OPENAI_API_KEY or USE_LLM_STUB=true")
    client, semaphore = _client_for_loop()
    try:
        async with semaphore:
            response = await client.chat.completions.create(
                model=settings.live_extract_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=settings.openai_temperature,
                response_format={"type": "json_object"},
            )
    except APIError as exc:
        code = getattr(exc, "status_code", None)
        detail = exc.__class__.__name__ if code is None else f"{exc.__class__.__name__} HTTP {code}"
        raise ExtractionError(f"Picked-up model failed: {detail}") from exc

    content = (response.choices[0].message.content or "").strip()
    fence = _JSON_FENCE_RE.search(content)
    if fence:
        content = fence.group(1).strip()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ExtractionError("Picked-up model returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ExtractionError("Picked-up model returned a non-object body")
    return payload
