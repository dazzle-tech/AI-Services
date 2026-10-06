"""OpenAI client for the Medical Document Processor pipeline.

Retry behavior mirrors LabResultInterpreterService's AIClient: transient errors
(rate limits, timeouts, connection errors) are retried up to `openai_max_retries`
attempts with backoff. Truncated JSON (token-limit cut-off) is retried once with a
higher max_tokens budget, then repaired if still incomplete. Other malformed JSON
fails after that recovery attempt.
"""
import base64
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from openai import APIError, APITimeoutError, APIConnectionError, OpenAI, RateLimitError

from app.core.config import settings
from app.ai.prompts import (
    build_classification_prompt,
    build_relevance_prompt,
    build_translation_prompt,
    build_validation_prompt,
)

logger = logging.getLogger(__name__)


class AIClient:
    """Client for interacting with OpenAI API for all four pipeline steps."""

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
        self.vision_model = settings.vision_model
        self.temperature = settings.openai_temperature
        self.max_tokens = settings.openai_max_tokens
        self.max_retries = settings.openai_max_retries
        self.retry_delay = settings.openai_retry_delay
        self.timeout = settings.openai_timeout

    # ------------------------------------------------------------------
    # Public pipeline-step methods
    # ------------------------------------------------------------------
    def validate_patient_match(
        self, patient: Dict[str, Any], extracted_text: str
    ) -> Dict[str, Any]:
        """Step 1: patient-match validation."""
        messages = build_validation_prompt(patient, extracted_text, settings.max_input_length)
        return self._call_json("patient-match validation", messages)

    def classify_relevance(
        self,
        extracted_text: str,
        relevance_windows_days: Dict[str, int],
        existing_documents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Step 2: relevance classification."""
        messages = build_relevance_prompt(
            extracted_text, relevance_windows_days, existing_documents, settings.max_input_length
        )
        return self._call_json("relevance classification", messages)

    def process_translation(
        self, extracted_text: str, translate_requested: bool, target_language: str
    ) -> Dict[str, Any]:
        """Step 3: language detection + conditional translation."""
        messages = build_translation_prompt(
            extracted_text, translate_requested, target_language, settings.max_input_length
        )
        # Translations of long documents can legitimately exceed the default max_tokens.
        return self._call_json(
            "translation", messages, max_tokens=max(self.max_tokens, 4000)
        )

    def classify_and_extract(self, extracted_text: str) -> Dict[str, Any]:
        """Step 4: document-type classification + loose structured extraction."""
        messages = build_classification_prompt(extracted_text, settings.max_input_length)
        # Lab panels and long notes routinely exceed the default 2000-token cap and
        # produce truncated JSON ("Expecting value" at EOF). Floor this step like
        # translation does.
        return self._call_json(
            "classification + extraction",
            messages,
            max_tokens=max(self.max_tokens, 8000),
        )

    def extract_text_from_image(self, image_bytes: bytes, mime_type: str) -> str:
        """OCR an image document via gpt-4o vision (primary OCR path, see image_extractor)."""
        b64 = base64.b64encode(image_bytes).decode("ascii")
        system = (
            "You transcribe the full text content of a photographed or scanned medical "
            "document image. Return the transcription as plain text, preserving line breaks, "
            "numeric values, units, and dosages exactly as shown. Do not summarize, translate, "
            "or add commentary -- output the raw transcribed text only."
        )
        last_exception: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.vision_model,
                    temperature=0,
                    max_tokens=self.max_tokens,
                    timeout=self.timeout,
                    messages=[
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Transcribe this document image."},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                                },
                            ],
                        },
                    ],
                )
                return (response.choices[0].message.content or "").strip()
            except RateLimitError as exc:
                last_exception = exc
                wait_time = self.retry_delay * (2**attempt)
                logger.warning("Vision OCR rate limited, retrying in %ss: %s", wait_time, exc)
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise ValueError(f"Rate limit exceeded after {self.max_retries} attempts") from exc
            except (APITimeoutError, APIConnectionError) as exc:
                last_exception = exc
                wait_time = self.retry_delay * (attempt + 1)
                logger.warning("Vision OCR connection error, retrying in %ss: %s", wait_time, exc)
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise ValueError(f"Vision OCR failed after {self.max_retries} attempts") from exc
            except APIError as exc:
                logger.error("OpenAI API error during vision OCR: %s", exc)
                raise ValueError(f"Vision OCR API error: {exc}") from exc
            except Exception as exc:  # noqa: BLE001
                logger.error("Unexpected error during vision OCR: %s", exc)
                raise ValueError(f"Vision OCR failed: {exc}") from exc

        raise ValueError(f"Vision OCR failed after {self.max_retries} attempts: {last_exception}")

    # ------------------------------------------------------------------
    # Shared JSON-mode call helper (retry policy shared by all 4 text steps)
    # ------------------------------------------------------------------
    def _call_json(
        self,
        step_name: str,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        last_exception: Optional[Exception] = None
        token_budget = max_tokens or self.max_tokens
        truncation_retries_left = 1
        for attempt in range(self.max_retries + truncation_retries_left):
            try:
                logger.debug(
                    "OpenAI call attempt %d for %s (max_tokens=%s)",
                    attempt + 1, step_name, token_budget,
                )
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=token_budget,
                    timeout=self.timeout,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError(f"Empty response from model during {step_name}")

                finish_reason = getattr(response.choices[0], "finish_reason", None)
                if settings.enable_usage_tracking and response.usage:
                    usage = response.usage
                    logger.info(
                        "%s token usage - prompt=%s completion=%s total=%s finish_reason=%s",
                        step_name,
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        usage.total_tokens,
                        finish_reason,
                    )

                try:
                    return self._parse_json(content, step_name)
                except ValueError as parse_exc:
                    truncated = finish_reason == "length" or self._looks_truncated(content)
                    if truncated and truncation_retries_left > 0:
                        truncation_retries_left -= 1
                        token_budget = min(max(token_budget * 2, 8000), 16384)
                        logger.warning(
                            "Truncated JSON during %s (finish_reason=%s); retrying with max_tokens=%s",
                            step_name, finish_reason, token_budget,
                        )
                        continue
                    repaired = self._repair_truncated_json(content)
                    if repaired is not None:
                        logger.warning("Repaired truncated JSON during %s", step_name)
                        return repaired
                    raise parse_exc

            except RateLimitError as exc:
                last_exception = exc
                wait_time = self.retry_delay * (2**attempt)
                logger.warning("Rate limit exceeded during %s, retrying in %ss: %s", step_name, wait_time, exc)
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise ValueError(f"Rate limit exceeded after {self.max_retries} attempts") from exc

            except (APITimeoutError, APIConnectionError) as exc:
                last_exception = exc
                wait_time = self.retry_delay * (attempt + 1)
                logger.warning("API connection error during %s, retrying in %ss: %s", step_name, wait_time, exc)
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise ValueError(
                        f"API connection failed after {self.max_retries} attempts: {exc}"
                    ) from exc

            except APIError as exc:
                logger.error("OpenAI API error during %s: %s", step_name, exc)
                raise ValueError(f"OpenAI API error during {step_name}: {exc}") from exc

            except ValueError:
                raise

            except Exception as exc:  # noqa: BLE001
                logger.error("Unexpected error during %s: %s", step_name, exc)
                raise ValueError(f"{step_name} failed: {exc}") from exc

        raise ValueError(f"Failed {step_name} after {self.max_retries} attempts: {last_exception}")

    @staticmethod
    def _looks_truncated(raw_output: str) -> bool:
        stripped = (raw_output or "").rstrip()
        if not stripped:
            return True
        return not stripped.endswith("}") and not stripped.endswith("]")

    @staticmethod
    def _repair_truncated_json(raw_output: str) -> Optional[Dict[str, Any]]:
        """Best-effort close of JSON cut off at a token limit (unclosed string/array/object)."""
        cleaned = (raw_output or "").strip()
        start = cleaned.find("{")
        if start < 0:
            return None
        text = cleaned[start:]

        in_string = False
        escape = False
        stack: List[str] = []
        for ch in text:
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in "}]":
                if stack and stack[-1] == ch:
                    stack.pop()

        if in_string:
            if escape:
                text = text[:-1]
            text += '"'

        text = text.rstrip()
        if text.endswith(","):
            text = text[:-1]

        while stack:
            text += stack.pop()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _parse_json(raw_output: str, step_name: str) -> Dict[str, Any]:
        cleaned = raw_output.strip()
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
            if match:
                cleaned = match.group(1).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end > start:
                try:
                    data = json.loads(cleaned[start : end + 1])
                except json.JSONDecodeError as exc:
                    logger.warning("Malformed JSON from model during %s: %s", step_name, exc)
                    raise ValueError(
                        f"Malformed JSON in model output during {step_name}: {exc}"
                    ) from exc
            else:
                logger.warning("Malformed JSON from model during %s", step_name)
                raise ValueError(f"Malformed JSON in model output during {step_name}")

        if not isinstance(data, dict):
            raise ValueError(f"Model output for {step_name} is not a JSON object")

        return data
