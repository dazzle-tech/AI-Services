"""OpenAI client for specialist alert generation."""
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError
from pydantic import ValidationError

from app.ai.prompts import build_alert_prompt
from app.core.config import settings
from app.models.schemas import Alert

logger = logging.getLogger(__name__)


class AlertParsingError(ValueError):
    """Raised when alert JSON cannot be parsed or validated."""


class AIClient:
    """Client for interacting with OpenAI API for specialist alerts."""

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

    def generate_alerts(
        self,
        patient_record: Dict[str, Any],
        risk_signals: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Alert]:
        """
        Generate structured alerts from patient record.

        Args:
            patient_record: Dictionary containing patient record
            risk_signals: Deterministic signals extracted from the record

        Returns:
            Validated list of Alert objects

        Raises:
            ValueError: If alert generation fails after retries
        """
        messages = build_alert_prompt(patient_record, risk_signals=risk_signals)

        # Adaptive token budget: starts at the configured max_tokens, but grows if a
        # response gets cut off by finish_reason="length" so the retry actually has
        # a chance of completing the JSON instead of truncating in the same place.
        current_max_tokens = self.max_tokens
        token_budget_cap = max(self.max_tokens * 4, 8000)
        truncated_last_attempt = False

        last_exception: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                logger.debug("OpenAI API call attempt %s/%s", attempt + 1, self.max_retries)
                prompt_length = len(json.dumps(messages, ensure_ascii=False))
                logger.info(
                    "Calling specialist alerts using model %s base_url=%s timeout=%ss "
                    "prompt_length=%s max_tokens=%s",
                    self.model,
                    self.base_url,
                    self.timeout,
                    prompt_length,
                    current_max_tokens,
                )

                extra_body = {}
                # Ollama/vLLM-only: disable local model thinking. OpenAI cloud
                # rejects unrecognized `chat_template_kwargs`.
                if (
                    settings.openai_disable_thinking
                    and self.base_url
                    and "11434" in self.base_url
                ):
                    extra_body["chat_template_kwargs"] = {"enable_thinking": False}

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=current_max_tokens,
                    timeout=self.timeout,
                    extra_body=extra_body or None,
                )

                choice = response.choices[0]
                content = choice.message.content
                finish_reason = getattr(choice, "finish_reason", None)
                truncated_last_attempt = finish_reason == "length"
                if truncated_last_attempt:
                    logger.warning(
                        "Model response was truncated by max_tokens (%s); "
                        "the reasoning trace may be consuming most of the budget.",
                        current_max_tokens,
                    )

                if not content:
                    raise AlertParsingError("Empty response from OpenAI model")

                content = self._strip_thinking(content)

                try:
                    alerts = self._parse_alerts(content)
                except AlertParsingError:
                    logger.warning(
                        "Raw model output that failed parsing (finish_reason=%s, len=%s): %s",
                        finish_reason,
                        len(content),
                        content[:2000],
                    )
                    raise

                if settings.enable_usage_tracking:
                    usage = response.usage
                    logger.info(
                        "Token usage - Prompt: %s, Completion: %s, Total: %s",
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        usage.total_tokens,
                    )

                return alerts

            except AlertParsingError as e:
                last_exception = e
                wait_time = self.retry_delay * (attempt + 1)
                if truncated_last_attempt and current_max_tokens < token_budget_cap:
                    previous_budget = current_max_tokens
                    current_max_tokens = min(int(current_max_tokens * 1.75), token_budget_cap)
                    logger.warning(
                        "Alert parsing failed after truncation, retrying in %ss with max_tokens "
                        "raised from %s to %s: %s",
                        wait_time,
                        previous_budget,
                        current_max_tokens,
                        e,
                    )
                else:
                    logger.warning("Alert parsing failed, retrying in %ss: %s", wait_time, e)
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise ValueError(
                        f"Malformed alert JSON after {self.max_retries} attempts: {str(e)}"
                    )

            except RateLimitError as e:
                last_exception = e
                wait_time = self.retry_delay * (2 ** attempt)
                logger.warning("Rate limit exceeded, retrying in %ss: %s", wait_time, e)
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise ValueError(f"Rate limit exceeded after {self.max_retries} attempts")

            except (APITimeoutError, APIConnectionError) as e:
                last_exception = e
                wait_time = self.retry_delay * (attempt + 1)
                logger.warning("API connection error, retrying in %ss: %s", wait_time, e)
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    raise ValueError(
                        f"API connection failed after {self.max_retries} attempts: {str(e)}"
                    )

            except APIError as e:
                logger.error("OpenAI API error: %s", e)
                raise ValueError(f"OpenAI API error: {str(e)}")

            except Exception as e:
                logger.error("Unexpected error in AI alert generation: %s", e)
                raise ValueError(f"AI alert generation failed: {str(e)}")

        raise ValueError(
            f"Failed to generate alerts after {self.max_retries} attempts: {str(last_exception)}"
        )

    def _parse_alerts(self, raw_output: str) -> List[Alert]:
        """Parse raw model output into validated alerts."""
        payload = self._extract_json_payload(raw_output)

        if isinstance(payload, dict) and "alerts" in payload:
            payload = payload["alerts"]
        elif isinstance(payload, dict):
            payload = [payload]

        if not isinstance(payload, list):
            raise AlertParsingError("AI response must be a JSON array of alerts")

        alerts: List[Alert] = []
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                logger.warning("Skipping non-dict alert item at position %s", index)
                continue

            normalized_item = self._normalize_alert_item(item, index)
            if not normalized_item:
                logger.warning("Skipping malformed alert item at position %s", index)
                continue

            try:
                alerts.append(Alert.model_validate(normalized_item))
            except ValidationError as exc:
                logger.warning("Skipping invalid alert item at position %s: %s", index, exc)

        if not alerts and payload:
            raise AlertParsingError("Model returned alert payload, but no items passed validation")
        return alerts

    def _strip_thinking(self, raw_output: str) -> str:
        """Remove <think>...</think> reasoning blocks emitted by reasoning models.

        Handles both a properly closed block and a block left open because the
        response was truncated by max_tokens before the model finished thinking.
        """
        text = raw_output
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # If a <think> tag was never closed (truncated mid-reasoning), there is no
        # JSON to recover from this response at all.
        if re.search(r"<think>", text, flags=re.IGNORECASE):
            raise AlertParsingError(
                "Model response was truncated inside its reasoning block before any "
                "JSON was produced; increase max_tokens or disable thinking mode"
            )
        return text.strip()

    def _extract_json_payload(self, raw_output: str) -> Any:
        """Extract JSON payload from raw model output."""
        cleaned = raw_output.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        for candidate in (cleaned, self._sanitize_json_text(cleaned)):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        array_start = cleaned.find("[")
        array_end = cleaned.rfind("]")
        if array_start != -1 and array_end != -1 and array_end > array_start:
            candidate = self._sanitize_json_text(cleaned[array_start : array_end + 1])
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                raise AlertParsingError(f"Unable to parse JSON array payload: {exc}") from exc

        object_start = cleaned.find("{")
        object_end = cleaned.rfind("}")
        if object_start != -1 and object_end != -1 and object_end > object_start:
            candidate = self._sanitize_json_text(cleaned[object_start : object_end + 1])
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                raise AlertParsingError(f"Unable to parse JSON object payload: {exc}") from exc

        raise AlertParsingError("Unable to extract JSON payload from AI response")

    def _normalize_alert_item(self, item: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
        """Normalize an alert payload before schema validation."""
        category = self._normalize_category(item.get("category"))
        if not category:
            return None

        supporting_evidence = self._normalize_supporting_evidence(item.get("supporting_evidence"))
        title = self._clean_text(item.get("title"))
        reason = self._clean_text(item.get("reason"))
        suggested_action = self._clean_text(item.get("suggested_action"))

        if not title or not reason or not suggested_action or not supporting_evidence:
            return None

        return {
            "alert_id": self._clean_text(item.get("alert_id")) or f"ALT-{index:03d}",
            "category": category,
            "severity": self._normalize_severity(item.get("severity")),
            "title": title,
            "reason": reason,
            "recommended_specialty": self._clean_optional_text(item.get("recommended_specialty")),
            "supporting_evidence": supporting_evidence,
            "suggested_action": suggested_action,
            "confidence": self._normalize_confidence(item.get("confidence")),
        }

    def _normalize_supporting_evidence(self, evidence: Any) -> List[str]:
        """Normalize supporting evidence into a list of strings."""
        if evidence is None:
            return []
        if isinstance(evidence, str):
            evidence = [evidence]
        if not isinstance(evidence, list):
            return []
        return [item for item in (self._clean_optional_text(v) for v in evidence) if item]

    def _normalize_category(self, value: Any) -> Optional[str]:
        """Normalize category labels to the supported schema."""
        normalized = self._simplify_label(value)
        if not normalized:
            return None

        category_map = {
            "specialist_consult": "specialist_consult",
            "specialist_consultation": "specialist_consult",
            "consult_recommendation": "specialist_consult",
            "critical_clinical_alert": "critical_clinical_alert",
            "critical_alert": "critical_clinical_alert",
            "medication_safety": "medication_safety",
            "medication_issue": "medication_safety",
            "lab_pattern_alert": "lab_pattern_alert",
            "lab_alert": "lab_pattern_alert",
            "imaging_follow_up": "imaging_follow_up",
            "imaging_followup": "imaging_follow_up",
            "care_gap": "care_gap",
            "duplicate_or_conflict": "duplicate_or_conflict",
            "duplicate_conflict": "duplicate_or_conflict",
            "urgent_escalation": "urgent_escalation",
            "missing_follow_up": "missing_follow_up",
            "missing_followup": "missing_follow_up",
        }

        if normalized in category_map:
            return category_map[normalized]
        if "duplicate" in normalized or "conflict" in normalized:
            return "duplicate_or_conflict"
        if "follow" in normalized and "imaging" in normalized:
            return "imaging_follow_up"
        if "follow" in normalized:
            return "missing_follow_up"
        if "consult" in normalized or "special" in normalized:
            return "specialist_consult"
        if "medication" in normalized or "drug" in normalized:
            return "medication_safety"
        if "lab" in normalized:
            return "lab_pattern_alert"
        if "care" in normalized or "gap" in normalized:
            return "care_gap"
        if "urgent" in normalized or "escalat" in normalized:
            return "urgent_escalation"
        if "critical" in normalized:
            return "critical_clinical_alert"
        return None

    def _normalize_severity(self, value: Any) -> str:
        """Normalize severity labels."""
        normalized = self._simplify_label(value)
        if normalized in {"critical", "severe", "immediate"}:
            return "critical"
        if normalized in {"high", "urgent"}:
            return "high"
        if normalized in {"medium", "moderate"}:
            return "medium"
        if normalized in {"low", "minor", "routine"}:
            return "low"
        return "medium"

    def _normalize_confidence(self, value: Any) -> str:
        """Normalize confidence labels."""
        normalized = self._simplify_label(value)
        if normalized in {"high", "very_high"}:
            return "high"
        if normalized in {"medium", "moderate"}:
            return "medium"
        if normalized in {"low", "limited", "uncertain"}:
            return "low"
        return "medium"

    def _simplify_label(self, value: Any) -> Optional[str]:
        """Normalize label formatting for comparisons."""
        cleaned = self._clean_optional_text(value)
        if cleaned is None:
            return None
        return cleaned.lower().replace("-", "_").replace(" ", "_")

    def _clean_text(self, value: Any) -> str:
        """Return a stripped string for required text fields."""
        cleaned = self._clean_optional_text(value)
        return cleaned or ""

    def _clean_optional_text(self, value: Any) -> Optional[str]:
        """Return a stripped string for optional fields."""
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    def _sanitize_json_text(self, json_text: str) -> str:
        """Sanitize common malformed JSON patterns."""
        sanitized = json_text.strip()
        sanitized = sanitized.replace("\u201c", "\"").replace("\u201d", "\"")
        sanitized = sanitized.replace("\u2018", "'").replace("\u2019", "'")
        sanitized = re.sub(r",(\s*[\]}])", r"\1", sanitized)
        return sanitized