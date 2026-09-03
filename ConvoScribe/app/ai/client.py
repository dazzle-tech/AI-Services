"""OpenAI client for structured JSON completions."""

import json
import logging
import re
import time
from typing import Any, Dict

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError

from app.core import config

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


class AIClient:
    """Client for interacting with OpenAI API."""

    def __init__(self) -> None:
        self._client = None
        if config.settings.openai_api_key and not config.settings.use_llm_stub:
            self._client = OpenAI(
                api_key=config.settings.openai_api_key,
                base_url=config.settings.openai_base_url or None,
                timeout=config.settings.openai_timeout,
                max_retries=config.settings.openai_max_retries,
            )
        self._temperature = config.settings.openai_temperature
        self._max_retries = max(config.settings.openai_max_retries, 1)
        self._retry_delay = config.settings.openai_retry_delay
        self._timeout = config.settings.openai_timeout

    def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> Dict[str, Any]:
        if self._client is None:
            raise RuntimeError("OpenAI client not configured; enable USE_LLM_STUB for offline mode")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        last_exception: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                response = self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=self._temperature,
                    timeout=self._timeout,
                    response_format={"type": "json_object"},
                )
                choice = response.choices[0]
                content = choice.message.content
                finish_reason = getattr(choice, "finish_reason", None)
                if not content:
                    raise ValueError(f"Empty response from model '{model}'")

                if config.settings.enable_usage_tracking and response.usage:
                    logger.info(
                        "OpenAI token usage model=%s prompt=%s completion=%s total=%s finish=%s",
                        model,
                        response.usage.prompt_tokens,
                        response.usage.completion_tokens,
                        response.usage.total_tokens,
                        finish_reason,
                    )

                return _parse_json_response(content)
            except RateLimitError as exc:
                last_exception = exc
                wait_time = self._retry_delay * (2**attempt)
                logger.warning("OpenAI rate limit, retrying in %ss", wait_time)
                if attempt < self._max_retries - 1:
                    time.sleep(wait_time)
            except (APITimeoutError, APIConnectionError) as exc:
                last_exception = exc
                wait_time = self._retry_delay * (attempt + 1)
                logger.warning("OpenAI connection error, retrying in %ss", wait_time)
                if attempt < self._max_retries - 1:
                    time.sleep(wait_time)
            except APIError:
                raise
            except json.JSONDecodeError as exc:
                last_exception = exc
                logger.warning("Invalid JSON from model (attempt %s): %s", attempt + 1, exc)
                if attempt < self._max_retries - 1:
                    continue
                raise ValueError(f"Invalid JSON response from OpenAI model: {exc}") from exc

        raise RuntimeError(
            f"OpenAI request failed after {self._max_retries} attempts: {last_exception}"
        )


def _parse_json_response(text: str) -> Dict[str, Any]:
    cleaned = (text or "").strip()
    fence = _JSON_FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    elif cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return json.loads(cleaned)
