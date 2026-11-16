"""OpenAI client for the three timeline steps."""
import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError
from pydantic import ValidationError

from app.ai.prompts import build_highlight_prompt, build_summary_prompt, build_timeline_prompt
from app.core.config import settings
from app.models.schemas import HighlightPayload, RoleHighlight, TimelineEvent, TimelineEventDraft

logger = logging.getLogger(__name__)


class ModelOutputError(ValueError):
    """Raised when model JSON cannot be parsed or validated."""


class AIClient:
    """Client for the timeline, summary, and highlight calls."""

    def __init__(self):
        """Initialize the OpenAI client from this service's settings."""
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set")
        if not settings.openai_model:
            raise ValueError("OPENAI_MODEL must be set")
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=settings.openai_timeout,
            max_retries=0,
        )
        self._completions = self.client.chat.completions
        self.base_url = settings.openai_base_url
        self.model = settings.openai_model
        self.temperature = settings.openai_temperature
        self.max_retries = settings.openai_max_retries
        self.retry_delay = settings.openai_retry_delay
        self.timeout = settings.openai_timeout
        self._send_temperature = True
        self._send_json_object = True

    def generate_timeline(self, patient_data: Dict[str, Any]) -> List[TimelineEventDraft]:
        """Ask the model for the shared timeline."""
        return self._complete(build_timeline_prompt(patient_data), self._parse_timeline)

    def generate_summary(
        self,
        events: Sequence[TimelineEvent],
        age: Optional[str],
        gender: Optional[str],
    ) -> str:
        """Ask the model for one summary of the timeline events."""
        payload = [event.model_dump() for event in events]
        return self._complete(build_summary_prompt(payload, age, gender), self._parse_summary)

    def generate_highlights(
        self,
        events: Sequence[TimelineEvent],
        viewer_role: str,
    ) -> Tuple[List[RoleHighlight], List[str]]:
        """Ask the model for role highlights of the timeline events."""
        payload = [event.model_dump() for event in events]
        parsed = self._complete(build_highlight_prompt(payload, viewer_role), self._parse_highlights)
        return parsed.role_highlights, parsed.not_documented

    def _complete(self, messages: List[Dict[str, str]], parser: Callable[[str], Any]) -> Any:
        """Call the model, validate JSON, then retry and repair."""
        last_error: Optional[Exception] = None
        last_raw = ""
        attempt = 0
        while attempt < self.max_retries:
            try:
                last_raw = self._invoke(messages)
                return parser(last_raw)
            except ModelOutputError as exc:
                last_error = exc
                attempt += 1
                logger.warning("Model JSON failed validation on attempt %s: %s", attempt, exc)
                if attempt >= self.max_retries:
                    return self._repair(messages, last_raw, last_error, parser)
                time.sleep(self.retry_delay * attempt)
            except RateLimitError as exc:
                attempt += 1
                logger.warning("Rate limit exceeded on attempt %s: %s", attempt, exc)
                if attempt >= self.max_retries:
                    raise ValueError(f"Rate limit exceeded after {self.max_retries} attempts") from exc
                time.sleep(self.retry_delay * (2 ** (attempt - 1)))
            except (APITimeoutError, APIConnectionError) as exc:
                attempt += 1
                logger.warning("API connection error on attempt %s: %s", attempt, exc)
                if attempt >= self.max_retries:
                    raise ValueError(
                        f"API connection failed after {self.max_retries} attempts: {exc}"
                    ) from exc
                time.sleep(self.retry_delay * attempt)
            except APIError as exc:
                logger.error("OpenAI API error: %s", exc)
                raise ValueError(f"OpenAI API error: {exc}") from exc
            except Exception as exc:
                logger.error("Unexpected OpenAI client error: %s", exc)
                raise ValueError(f"OpenAI request failed: {exc}") from exc

        raise ValueError(f"OpenAI request failed after {self.max_retries} attempts: {last_error}")

    def _repair(
        self,
        messages: List[Dict[str, str]],
        raw_output: str,
        error: Optional[Exception],
        parser: Callable[[str], Any],
    ) -> Any:
        """One repair call for malformed JSON."""
        try:
            repaired = self._invoke(self._repair_messages(messages, raw_output, error))
            return parser(repaired)
        except ModelOutputError as exc:
            raise ValueError(
                f"Malformed model JSON after {self.max_retries} attempts and one repair: {exc}"
            ) from exc
        except (APITimeoutError, APIConnectionError, RateLimitError, APIError) as exc:
            raise ValueError(f"OpenAI request failed: {exc}") from exc

    def _repair_messages(
        self,
        messages: List[Dict[str, str]],
        raw_output: str,
        error: Optional[Exception],
    ) -> List[Dict[str, str]]:
        """Ask the model to return corrected JSON without new clinical facts."""
        return list(messages) + [
            {"role": "assistant", "content": raw_output or ""},
            {
                "role": "user",
                "content": (
                    "The previous response was not valid JSON for the required schema. "
                    f"Error: {error}. Return only the corrected JSON object. "
                    "Do not add clinical facts that were absent from the source message."
                ),
            },
        ]

    def _invoke(self, messages: List[Dict[str, str]]) -> str:
        """Send one chat completion, dropping parameters the model rejects."""
        while True:
            try:
                response = self._completions.create(**self._request_kwargs(messages))
                break
            except APIError as exc:
                if self._relax_parameters(exc):
                    logger.info("Retrying without an unsupported OpenAI parameter: %s", exc)
                    continue
                raise

        if settings.enable_usage_tracking and getattr(response, "usage", None) is not None:
            usage = response.usage
            logger.info(
                "Token usage - Prompt: %s, Completion: %s, Total: %s",
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
            )

        message = response.choices[0].message
        content = message.content or ""
        if not content.strip():
            raise ModelOutputError("Empty response from model")
        logger.info("Model content received (%s characters)", len(content))
        return content

    def _request_kwargs(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Build a chat completion request from this service's settings."""
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "timeout": self.timeout,
        }
        if self._send_temperature:
            kwargs["temperature"] = self.temperature
        if self._send_json_object:
            kwargs["response_format"] = {"type": "json_object"}
        return kwargs

    def _relax_parameters(self, exc: APIError) -> bool:
        """Drop temperature or JSON mode when this model rejects them."""
        message = str(exc).lower()
        relaxed = False
        if self._send_temperature and "temperature" in message:
            self._send_temperature = False
            relaxed = True
        if self._send_json_object and ("response_format" in message or "json_object" in message):
            self._send_json_object = False
            relaxed = True
        return relaxed

    def _parse_timeline(self, raw_output: str) -> List[TimelineEventDraft]:
        """Validate the timeline object."""
        payload = self._load_json_object(raw_output)
        if isinstance(payload, list):
            payload = {"events": payload}
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            raise ModelOutputError("Timeline response must contain an events array")
        try:
            return [TimelineEventDraft.model_validate(item) for item in events]
        except ValidationError as exc:
            raise ModelOutputError(f"Timeline response validation failed: {exc}") from exc

    def _parse_summary(self, raw_output: str) -> str:
        """Validate the summary object."""
        payload = self._load_json_object(raw_output)
        if not isinstance(payload, dict):
            raise ModelOutputError("Summary response must be a JSON object")
        summary = payload.get("clinical_summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ModelOutputError("clinical_summary must be a non-empty string")
        return summary.strip()

    def _parse_highlights(self, raw_output: str) -> HighlightPayload:
        """Validate the highlight object."""
        payload = self._load_json_object(raw_output)
        if isinstance(payload, list):
            payload = {"role_highlights": payload, "not_documented": []}
        if not isinstance(payload, dict):
            raise ModelOutputError("Highlight response must be a JSON object")
        try:
            return HighlightPayload.model_validate(payload)
        except ValidationError as exc:
            raise ModelOutputError(f"Highlight response validation failed: {exc}") from exc

    def _load_json_object(self, raw_output: str) -> Any:
        """Extract and sanitize a JSON object from model text."""
        json_text = self._extract_json(raw_output)
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            sanitized = self._sanitize_json_text(json_text)
            try:
                return json.loads(sanitized)
            except json.JSONDecodeError as exc:
                raise ModelOutputError(f"Unable to parse model JSON: {exc}") from exc

    def _extract_json(self, raw_output: str) -> str:
        """Extract the JSON payload from fenced or prefixed model text."""
        cleaned = raw_output.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()
        if cleaned.startswith("{") or cleaned.startswith("["):
            return cleaned
        object_at = cleaned.find("{")
        array_at = cleaned.find("[")
        starts = [index for index in (object_at, array_at) if index != -1]
        if not starts:
            raise ModelOutputError("Model response does not contain JSON")
        start = min(starts)
        end = cleaned.rfind("}") if cleaned[start] == "{" else cleaned.rfind("]")
        if end <= start:
            raise ModelOutputError("Model response does not contain JSON")
        return cleaned[start:end + 1]

    def _sanitize_json_text(self, json_text: str) -> str:
        """Repair quotes and trailing commas that models commonly emit."""
        sanitized = json_text.strip()
        sanitized = sanitized.replace("\u201c", '"').replace("\u201d", '"')
        sanitized = sanitized.replace("\u2018", "'").replace("\u2019", "'")
        sanitized = re.sub(r",(\s*[\]}])", r"\1", sanitized)
        return sanitized
