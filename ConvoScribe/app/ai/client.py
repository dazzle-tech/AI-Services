"""OpenAI client for structured JSON completions."""

import json
import logging
import re
import time
from typing import Any, Dict

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError

from app.core import config

logger = logging.getLogger(__name__)


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
        self._max_tokens = config.settings.openai_max_tokens
        self._max_retries = config.settings.openai_max_retries
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
                    max_tokens=self._max_tokens,
                    timeout=self._timeout,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError(f"Empty response from model '{model}'")

                if config.settings.enable_usage_tracking and response.usage:
                    logger.info(
                        "OpenAI token usage model=%s prompt=%s completion=%s total=%s",
                        model,
                        response.usage.prompt_tokens,
                        response.usage.completion_tokens,
                        response.usage.total_tokens,
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
                raise ValueError(f"Invalid JSON response from OpenAI model: {exc}") from exc

        raise RuntimeError(
            f"OpenAI request failed after {self._max_retries} attempts: {last_exception}"
        )


def _parse_json_response(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return json.loads(cleaned)
