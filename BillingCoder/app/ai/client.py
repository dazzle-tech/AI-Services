"""OpenAI client for CodingAssist analysis."""
import json
import logging
import time
from typing import Any, Dict

from openai import OpenAI
from openai import APIError, RateLimitError, APITimeoutError, APIConnectionError

from app.core.config import settings

logger = logging.getLogger(__name__)


class CodingAIClient:
    """Thin wrapper around the OpenAI SDK with retry logic."""

    def __init__(self):
        """Construct the OpenAI client using configured credentials."""
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set")
        client_kwargs = {
            "api_key": settings.openai_api_key,
            "timeout": settings.openai_timeout,
        }
        if settings.openai_base_url:
            client_kwargs["base_url"] = settings.openai_base_url
        self.client = OpenAI(**client_kwargs)
        self.model = settings.openai_model
        self.temperature = settings.openai_temperature
        self.max_retries = settings.openai_max_retries
        self.retry_delay = settings.openai_retry_delay

    def analyze(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Send the prompt pair to OpenAI and return parsed JSON.

        Args:
            system_prompt: The system role content.
            user_prompt: The user role content.

        Returns:
            The model's JSON response parsed into a dict.

        Raises:
            ValueError: On invalid JSON, empty response, persistent API errors,
                or retry exhaustion.
        """
        last_exception: Exception = RuntimeError("no attempt made")
        for attempt in range(self.max_retries):
            try:
                logger.info("OpenAI API call attempt %d/%d", attempt + 1, self.max_retries)
                response = self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                raw = response.choices[0].message.content
                if not raw:
                    raise ValueError("Empty response from model")
                result = json.loads(raw)
                if hasattr(response, "usage") and response.usage:
                    usage = response.usage
                    logger.info(
                        "Token usage - Prompt: %d, Completion: %d, Total: %d",
                        usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
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
