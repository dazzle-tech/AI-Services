"""OpenAI client for SepsisSentinel sepsis risk analysis."""
import json
import logging
import time

from openai import OpenAI
from openai import APIError, RateLimitError, APITimeoutError, APIConnectionError

from app.core.config import settings

logger = logging.getLogger(__name__)


class SepsisAIClient:
    """Client for interacting with the OpenAI API for sepsis analysis."""

    def __init__(self):
        """Initialise the OpenAI client using application settings."""
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set")
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=settings.openai_timeout,
            max_retries=settings.openai_max_retries,
        )
        self.base_url = settings.openai_base_url or "https://api.openai.com/v1"
        self.model = settings.openai_model
        self.temperature = settings.openai_temperature
        self.max_retries = settings.openai_max_retries
        self.retry_delay = settings.openai_retry_delay
        self.timeout = settings.openai_timeout

    def analyze(self, system_prompt: str, user_prompt: str) -> dict:
        """Send prompts to GPT-4o and return the parsed JSON response.

        Args:
            system_prompt: The system-role prompt string.
            user_prompt: The user-role prompt string.

        Returns:
            Parsed dict from the model's JSON response.

        Raises:
            ValueError: If analysis fails after all retries.
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                logger.info(
                    "OpenAI API call attempt %d/%d",
                    attempt + 1,
                    self.max_retries,
                )
                prompt_length = len(system_prompt) + len(user_prompt)
                logger.info(
                    "Calling sepsis analysis using model %s base_url=%s timeout=%ss prompt_length=%s",
                    self.model,
                    self.base_url,
                    self.timeout,
                    prompt_length,
                )

                response = self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    timeout=self.timeout,
                )

                raw = response.choices[0].message.content
                if not raw:
                    raise ValueError("Empty response from model")

                result = json.loads(raw)

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
                logger.warning(
                    "Rate limit exceeded, retrying in %.1fs: %s",
                    wait_time,
                    exc,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)

            except (APITimeoutError, APIConnectionError) as exc:
                last_exception = exc
                wait_time = self.retry_delay * (attempt + 1)
                logger.warning(
                    "API connection error, retrying in %.1fs: %s",
                    wait_time,
                    exc,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)

            except APIError as exc:
                logger.error("OpenAI API error: %s", exc)
                raise ValueError(f"OpenAI API error: {exc}") from exc

            except json.JSONDecodeError as exc:
                logger.error("Failed to parse model response as JSON: %s", exc)
                raise ValueError(
                    f"Model returned invalid JSON: {exc}"
                ) from exc

        raise ValueError(
            f"Failed after {self.max_retries} attempts: {last_exception}"
        )
