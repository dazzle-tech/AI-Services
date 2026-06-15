"""OpenAI client wrapper for structured OCR extraction."""
import json
import logging
import time
from typing import Any

try:
    from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError
except ImportError:  # pragma: no cover
    APIConnectionError = APIError = APITimeoutError = RateLimitError = Exception  # type: ignore[assignment]
    OpenAI = None  # type: ignore[assignment]

from app.core.config import settings

logger = logging.getLogger(__name__)


class StructuredOutputClient:
    """Thin wrapper around the OpenAI SDK with retry handling."""

    def __init__(self) -> None:
        self.api_key = settings.openai_api_key.strip()
        self.model = settings.openai_model
        self.temperature = settings.openai_temperature
        self.timeout = settings.openai_timeout
        self.max_retries = settings.openai_max_retries
        self.retry_delay = settings.openai_retry_delay
        self.client = None
        if self.api_key and OpenAI is not None:
            self.client = OpenAI(api_key=self.api_key, timeout=self.timeout)

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Send a JSON-mode request and return the parsed object."""
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY must be set")
        if OpenAI is None:  # pragma: no cover
            raise RuntimeError("openai package is not installed")
        if self.client is None:
            self.client = OpenAI(api_key=self.api_key, timeout=self.timeout)

        last_exception: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                logger.info("OpenAI API call attempt %d/%d", attempt + 1, self.max_retries)
                start_time = time.monotonic()
                response = self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
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

            except RateLimitError as exc:
                last_exception = exc
                wait_time = self.retry_delay * (2 ** attempt)
                logger.warning("Rate limit, retrying in %.1fs: %s", wait_time, exc)
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)

            except (APITimeoutError, APIConnectionError) as exc:
                last_exception = exc
                wait_time = self.retry_delay * (attempt + 1)
                logger.warning("Connection error, retrying in %.1fs: %s", wait_time, exc)
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)

            except APIError as exc:
                raise ValueError(f"OpenAI API error: {exc}") from exc

            except json.JSONDecodeError as exc:
                raise ValueError(f"Model returned invalid JSON: {exc}") from exc

        raise ValueError(f"Failed after {self.max_retries} attempts: {last_exception}")
