"""OpenAI client wrapper for structured OCR extraction."""
import json
import logging
import time
from typing import Any

try:
    from openai import (
        APIConnectionError,
        APIError,
        APITimeoutError,
        AuthenticationError,
        OpenAI,
        RateLimitError,
    )
except ImportError:  # pragma: no cover
    APIConnectionError = APIError = APITimeoutError = AuthenticationError = RateLimitError = Exception  # type: ignore[assignment]
    OpenAI = None  # type: ignore[assignment]

from app.core.config import settings

logger = logging.getLogger(__name__)


class OCRUnavailable(Exception):
    """The vision provider cannot be called. The message stays empty so it cannot carry image data."""


class StructuredOutputClient:
    """Thin wrapper around the OpenAI SDK with retry handling."""

    def __init__(self) -> None:
        self.api_key = settings.openai_api_key.strip()
        self.model = settings.openai_model
        self.base_url = settings.openai_base_url or "https://api.openai.com/v1"
        self.temperature = settings.openai_temperature
        self.timeout = settings.openai_timeout
        self.max_retries = settings.openai_max_retries
        self.retry_delay = settings.openai_retry_delay
        self.client = None
        if self.api_key and OpenAI is not None:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=settings.openai_base_url or None,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Send a JSON-mode request and return the parsed object."""
        return self._complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )

    def generate_vision_json(
        self,
        system_prompt: str,
        user_prompt: str,
        image_data_url: str,
        *,
        image_bytes: int,
    ) -> dict[str, Any]:
        """Send an image plus instructions and return the parsed JSON object."""
        return self._complete(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_url, "detail": settings.vision_detail},
                        },
                    ],
                },
            ],
            image_bytes=image_bytes,
            temperature=0,
            timeout=settings.openai_vision_timeout,
            model=settings.vision_model,
            vision=True,
        )

    def _complete(
        self,
        messages: list[dict[str, Any]],
        *,
        image_bytes: int | None = None,
        temperature: float | None = None,
        timeout: int | None = None,
        model: str | None = None,
        vision: bool = False,
    ) -> dict[str, Any]:
        if not self.api_key:
            if vision:
                raise OCRUnavailable()
            raise ValueError("OPENAI_API_KEY must be set")
        if OpenAI is None:  # pragma: no cover
            raise RuntimeError("openai package is not installed")
        if self.client is None:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=settings.openai_base_url or None,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )

        call_model = model or self.model
        call_timeout = self.timeout if timeout is None else timeout
        call_temperature = self.temperature if temperature is None else temperature
        last_exception: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                logger.info("OpenAI API call attempt %d/%d", attempt + 1, self.max_retries)
                logger.info(
                    "Calling model %s base_url=%s timeout=%ss text_chars=%s image_bytes=%s",
                    call_model,
                    self.base_url,
                    call_timeout,
                    _text_length(messages),
                    image_bytes,
                )
                start_time = time.monotonic()
                response = self.client.chat.completions.create(
                    model=call_model,
                    temperature=call_temperature,
                    response_format={"type": "json_object"},
                    messages=messages,
                    timeout=call_timeout,
                )
                elapsed_seconds = time.monotonic() - start_time
                logger.info("OpenAI request finished in %.2fs", elapsed_seconds)

                raw = response.choices[0].message.content
                if not raw:
                    raise ValueError("Empty response from model")

                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ValueError("Model returned a JSON value that is not an object")

                if hasattr(response, "usage") and response.usage:
                    usage = response.usage
                    logger.info(
                        "Token usage - Prompt: %d, Completion: %d, Total: %d",
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        usage.total_tokens,
                    )
                return result

            except AuthenticationError:
                logger.warning("OpenAI authentication failed type=AuthenticationError")
                if vision:
                    raise OCRUnavailable() from None
                raise

            except RateLimitError as exc:
                last_exception = exc
                wait_time = self.retry_delay * (2 ** attempt)
                logger.warning("OpenAI rate limit type=%s", type(exc).__name__)
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)

            except (APITimeoutError, APIConnectionError) as exc:
                last_exception = exc
                wait_time = self.retry_delay * (attempt + 1)
                logger.warning("OpenAI connection failure type=%s", type(exc).__name__)
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)

            except APIError:
                logger.warning("OpenAI API error type=APIError")
                if vision:
                    raise OCRUnavailable() from None
                raise RuntimeError("OpenAI request failed") from None

            except json.JSONDecodeError:
                raise ValueError("Model returned invalid JSON") from None

        logger.warning(
            "OpenAI request failed type=%s",
            type(last_exception).__name__ if last_exception else "None",
        )
        if vision:
            raise OCRUnavailable() from None
        raise RuntimeError("OpenAI request failed") from None


def _text_length(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            total += len(content)
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                total += len(str(part.get("text") or ""))
    return total
