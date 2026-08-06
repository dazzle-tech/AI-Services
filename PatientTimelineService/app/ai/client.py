"""OpenAI client for patient timeline generation."""
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI
from openai import APIError, APIConnectionError, APITimeoutError, RateLimitError
from pydantic import ValidationError

from app.ai.prompts import build_timeline_prompt
from app.core.config import settings
from app.models.schemas import TimelineEvent

logger = logging.getLogger(__name__)


class TimelineParsingError(ValueError):
    """Raised when timeline JSON cannot be parsed or validated."""


class AIClient:
    """Client for interacting with OpenAI API."""

    def __init__(self):
        """Initialize OpenAI client."""
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
        self.max_tokens = settings.openai_max_tokens
        self.max_retries = settings.openai_max_retries
        self.retry_delay = settings.openai_retry_delay
        self.timeout = settings.openai_timeout

    def generate_timeline(self, patient_data: Dict[str, Any]) -> List[TimelineEvent]:
        """
        Generate a patient timeline from patient data using OpenAI.

        Args:
            patient_data: Dictionary containing patient information

        Returns:
            List of validated timeline events

        Raises:
            ValueError: If timeline generation fails after retries
        """
        messages = build_timeline_prompt(patient_data)

        last_exception: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"OpenAI API call attempt {attempt + 1}/{self.max_retries}")
                prompt_length = len(json.dumps(messages, ensure_ascii=False))
                logger.info(
                    "Calling patient timeline using model %s base_url=%s timeout=%ss prompt_length=%s",
                    self.model,
                    self.base_url,
                    self.timeout,
                    prompt_length,
                )

                create_kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "timeout": self.timeout,
                }
                # Ollama-only: disable thinking so local reasoning models don't
                # burn max_tokens on <think> and leave an empty JSON answer.
                # OpenAI cloud rejects unrecognized `reasoning_effort`.
                if self.base_url and "11434" in self.base_url:
                    create_kwargs["extra_body"] = {"reasoning_effort": "none"}

                response = self.client.chat.completions.create(**create_kwargs)

                message = response.choices[0].message
                content = message.content
                logger.info(
                    "Raw model content received (%d chars); preview: %r",
                    len(content or ""), (content or "")[:200],
                )
                if not content:
                    # Some OpenAI-compatible servers (notably Ollama with
                    # reasoning-capable models like Qwen3) surface chain-of-thought
                    # text in a separate `reasoning_content` field and leave
                    # `content` empty if generation is cut off mid-thought before
                    # reaching the actual answer. Fall back to it for visibility,
                    # but treat it as a signal, not a valid payload.
                    reasoning = getattr(message, "reasoning_content", None) or getattr(message, "reasoning", None)
                    if reasoning:
                        logger.warning(
                            "Model returned only reasoning content (%d chars) and no final "
                            "answer, likely truncated by max_tokens=%s while thinking.",
                            len(reasoning), self.max_tokens,
                        )
                    raise TimelineParsingError("Empty response from model")

                timeline = self._parse_timeline(content)

                if settings.enable_usage_tracking:
                    usage = response.usage
                    logger.info(
                        f"Token usage - Prompt: {usage.prompt_tokens}, "
                        f"Completion: {usage.completion_tokens}, "
                        f"Total: {usage.total_tokens}"
                    )

                return timeline

            except TimelineParsingError as e:
                last_exception = e
                wait_time = self.retry_delay * (attempt + 1)
                logger.warning(f"Timeline parsing failed, retrying in {wait_time}s: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise ValueError(
                        f"Malformed timeline JSON after {self.max_retries} attempts: {str(e)}"
                    )

            except RateLimitError as e:
                last_exception = e
                wait_time = self.retry_delay * (2 ** attempt)
                logger.warning(f"Rate limit exceeded, retrying in {wait_time}s: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise ValueError(f"Rate limit exceeded after {self.max_retries} attempts")

            except (APITimeoutError, APIConnectionError) as e:
                last_exception = e
                wait_time = self.retry_delay * (attempt + 1)
                logger.warning(f"API connection error, retrying in {wait_time}s: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise ValueError(
                        f"API connection failed after {self.max_retries} attempts: {str(e)}"
                    )

            except APIError as e:
                logger.error(f"OpenAI API error: {e}")
                raise ValueError(f"OpenAI API error: {str(e)}")

            except Exception as e:
                logger.error(f"Unexpected error in AI timeline generation: {e}")
                raise ValueError(f"AI timeline generation failed: {str(e)}")

        raise ValueError(
            f"Failed to generate timeline after {self.max_retries} attempts: {str(last_exception)}"
        )

    def _parse_timeline(self, raw_output: str) -> List[TimelineEvent]:
        """Parse, sanitize, and validate timeline JSON."""
        json_text = self._extract_json_array(raw_output)

        try:
            payload = json.loads(json_text)
        except json.JSONDecodeError:
            sanitized_text = self._sanitize_json_text(json_text)
            try:
                payload = json.loads(sanitized_text)
            except json.JSONDecodeError as exc:
                raise TimelineParsingError(f"Unable to parse timeline JSON: {exc}") from exc

        if not isinstance(payload, list):
            raise TimelineParsingError("Timeline response must be a JSON array")

        try:
            return [TimelineEvent.model_validate(item) for item in payload]
        except ValidationError as exc:
            raise TimelineParsingError(f"Timeline response validation failed: {exc}") from exc

    def _extract_json_array(self, raw_output: str) -> str:
        """Extract the JSON array from model output."""
        cleaned = raw_output.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        # Strip any reasoning block some servers inline into `content`
        # (e.g. Qwen3 on Ollama emits `<think>...</think>` before the answer).
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()

        if cleaned.startswith("[") and cleaned.endswith("]"):
            return cleaned

        start_idx = cleaned.find("[")
        end_idx = cleaned.rfind("]")
        if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
            raise TimelineParsingError("Model response does not contain a JSON array")

        return cleaned[start_idx:end_idx + 1]

    def _sanitize_json_text(self, json_text: str) -> str:
        """Sanitize common malformed JSON patterns."""
        sanitized = json_text.strip()
        sanitized = sanitized.replace("\u201c", "\"").replace("\u201d", "\"")
        sanitized = sanitized.replace("\u2018", "'").replace("\u2019", "'")
        sanitized = re.sub(r",(\s*[\]}])", r"\1", sanitized)
        return sanitized
