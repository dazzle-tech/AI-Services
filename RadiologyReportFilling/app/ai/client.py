"""OpenAI client wrapper for Medical Imaging Assist with retry logic."""
import json
import logging
import re
import time

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError

from app.core.config import settings
from app.ai.model_resolver import model_not_found, resolve_fallback_model

logger = logging.getLogger(__name__)
_THINK_BLOCK_RE = re.compile(r"^\s*<think>.*?</think>\s*", re.IGNORECASE | re.DOTALL)


def _strip_model_wrappers(raw_text: str) -> str:
    clean = _THINK_BLOCK_RE.sub("", raw_text.strip(), count=1)
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        clean = clean.rsplit("```", 1)[0]
    return clean.strip()


def _extract_first_json_object(raw_text: str) -> str | None:
    start = -1
    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(raw_text):
        if start < 0:
            if char == "{":
                start = index
                depth = 1
            continue

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return raw_text[start : index + 1]
    return None


def _parse_json_object(raw_text: str) -> dict:
    cleaned = _strip_model_wrappers(raw_text)
    candidate = cleaned if cleaned.startswith("{") else _extract_first_json_object(cleaned)
    if not candidate:
        raise json.JSONDecodeError("No JSON object found in model response", cleaned, 0)
    return json.loads(candidate)


class MedicalAIClient:
    """Thin wrapper around the OpenAI SDK with JSON-mode + retry handling."""

    def __init__(self) -> None:
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
        self._resolved_model: str | None = None
        self.temperature = settings.openai_temperature
        self.max_retries = settings.openai_max_retries
        self.retry_delay = settings.openai_retry_delay
        self.timeout = settings.openai_timeout

    def analyze(self, system_prompt: str, user_prompt: str) -> dict:
        """Send prompts to OpenAI in JSON mode and return parsed JSON.

        Args:
            system_prompt: The role/task/rules block injected as the system message.
            user_prompt: The data + instruction block injected as the user message.

        Returns:
            The parsed JSON dict returned by the model.

        Raises:
            ValueError: On invalid JSON, exhausted retries, or non-retryable API errors.
        """
        last_exception: Exception | None = None
        for attempt in range(self.max_retries):
            model_name = self._resolved_model or self.model
            try:
                prompt_length = len(system_prompt) + len(user_prompt)
                logger.info(
                    "OpenAI API call attempt %d/%d using model %s base_url=%s timeout=%ss prompt_length=%s",
                    attempt + 1,
                    self.max_retries,
                    model_name,
                    self.base_url,
                    self.timeout,
                    prompt_length,
                )
                response = self.client.chat.completions.create(
                    model=model_name,
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
                logger.info("Report filling raw model response length=%d", len(raw))
                try:
                    result = _parse_json_object(raw)
                    logger.info("Report filling JSON parsing success=true")
                except json.JSONDecodeError as exc:
                    logger.warning("Report filling JSON parsing success=false error=%s", exc)
                    raise ValueError(f"Model returned invalid JSON: {exc}") from exc
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
                if model_not_found(exc):
                    fallback_model = resolve_fallback_model(self.client, model_name)
                    if fallback_model and fallback_model != model_name:
                        self._resolved_model = fallback_model
                        last_exception = exc
                        continue
                raise ValueError(f"OpenAI API error: {exc}") from exc

        raise ValueError(f"Failed after {self.max_retries} attempts: {last_exception}")
