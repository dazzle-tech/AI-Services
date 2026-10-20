"""One small JSON completion for the picked-up list (LIVE_EXTRACT_MODEL, any OpenAI-compatible endpoint)."""

from __future__ import annotations

import json
import re
from typing import Any

from openai import APIError, AsyncOpenAI

from app.core.config import settings

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


class ExtractionError(RuntimeError):
    """The picked-up model is missing, failed, or returned something unusable."""


def is_configured() -> bool:
    return settings.use_llm_stub or bool(settings.openai_api_key)


async def complete_json(*, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    if not settings.openai_api_key:
        raise ExtractionError("Picked-up model is not configured: set OPENAI_API_KEY or USE_LLM_STUB=true")
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        timeout=settings.openai_timeout_seconds,
        max_retries=0,
    )
    try:
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
        raise ExtractionError(f"Picked-up model failed: {exc.__class__.__name__}") from exc
    finally:
        await client.close()

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
