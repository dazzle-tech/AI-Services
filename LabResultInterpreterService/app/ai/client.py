"""OpenAI client for lab result interpretation."""
import json
import logging
import re
import time
from typing import Dict, Any, List, Optional
from openai import OpenAI
from openai import APIError, RateLimitError, APITimeoutError, APIConnectionError
from app.core.config import settings
from app.ai.prompts import build_lab_interpretation_prompt

logger = logging.getLogger(__name__)


class AIClient:
    """Client for interacting with OpenAI API for lab interpretation."""

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
        self.max_retries = settings.openai_max_retries
        self.retry_delay = settings.openai_retry_delay
        self.timeout = settings.openai_timeout

    def interpret_labs(
        self,
        patient_context: Optional[Dict[str, Any]],
        lab_results: List[Dict[str, Any]],
        historical_lab_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Interpret lab results using GPT-4.

        Args:
            patient_context: Optional patient context dict
            lab_results: List of current lab result dicts
            historical_lab_results: List of historical lab result dicts

        Returns:
            Parsed interpretation dict with severity, key_findings, patterns, trends, etc.

        Raises:
            ValueError: If interpretation fails after retries or output is malformed
        """
        messages = build_lab_interpretation_prompt(
            patient_context, lab_results, historical_lab_results
        )

        last_exception = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"OpenAI API call attempt {attempt + 1}/{self.max_retries}")
                prompt_length = len(json.dumps(messages, ensure_ascii=False))
                logger.info(
                    "Calling lab interpretation using model %s base_url=%s timeout=%ss prompt_length=%s",
                    self.model,
                    self.base_url,
                    self.timeout,
                    prompt_length,
                )

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    timeout=self.timeout,
                )

                content = response.choices[0].message.content

                if not content:
                    raise ValueError("Empty response from model")

                interpretation = self._parse_and_normalize(content)

                if settings.enable_usage_tracking:
                    usage = response.usage
                    logger.info(
                        f"Token usage - Prompt: {usage.prompt_tokens}, "
                        f"Completion: {usage.completion_tokens}, "
                        f"Total: {usage.total_tokens}"
                    )

                return interpretation

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

            except ValueError as e:
                if "Empty response" in str(e) or "malformed" in str(e).lower():
                    raise
                last_exception = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise

            except Exception as e:
                logger.error(f"Unexpected error in AI lab interpretation: {e}")
                raise ValueError(f"AI lab interpretation failed: {str(e)}")

        raise ValueError(
            f"Failed to interpret labs after {self.max_retries} attempts: {str(last_exception)}"
        )

    def _parse_and_normalize(self, raw_output: str) -> Dict[str, Any]:
        """
        Parse JSON from raw LLM output and normalize to expected schema.
        Handles markdown code blocks and common formatting issues.
        """
        cleaned = raw_output.strip()

        # Remove markdown code blocks if present
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
            if match:
                cleaned = match.group(1).strip()

        # Try to parse JSON
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from model output: {e}")
            raise ValueError(f"Malformed JSON in model output: {str(e)}")

        if not isinstance(data, dict):
            raise ValueError("Model output is not a JSON object")

        # Normalize to expected schema
        return self._normalize_interpretation(data)

    def _normalize_interpretation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize interpretation structure."""
        result: Dict[str, Any] = {
            "severity": "moderate",
            "key_findings": [],
            "patterns": [],
            "trends": [],
            "follow_up_considerations": [],
            "disclaimer": "This output is interpretation support and not a diagnosis.",
        }

        # Severity
        severity = data.get("severity", "moderate")
        if isinstance(severity, str) and severity.lower() in ("low", "moderate", "high", "critical"):
            result["severity"] = severity.lower()
        elif isinstance(severity, str):
            result["severity"] = severity

        # Key findings
        kf = data.get("key_findings", [])
        if isinstance(kf, list):
            result["key_findings"] = [str(x) for x in kf if x]
        elif isinstance(kf, str):
            result["key_findings"] = [kf] if kf.strip() else []

        # Patterns
        patterns = data.get("patterns", [])
        if isinstance(patterns, list):
            for p in patterns:
                if isinstance(p, dict) and p.get("label") and p.get("reason"):
                    result["patterns"].append({
                        "label": str(p["label"]),
                        "reason": str(p["reason"]),
                    })
                elif isinstance(p, dict):
                    result["patterns"].append({
                        "label": str(p.get("label", "unknown")),
                        "reason": str(p.get("reason", "")),
                    })

        # Trends
        trends = data.get("trends", [])
        if isinstance(trends, list):
            for t in trends:
                if isinstance(t, dict):
                    result["trends"].append({
                        "lab_name": str(t.get("lab_name", "")),
                        "direction": str(t.get("direction", "stable")),
                        "summary": str(t.get("summary", "")),
                    })

        # Follow-up considerations
        fu = data.get("follow_up_considerations", [])
        if isinstance(fu, list):
            result["follow_up_considerations"] = [str(x) for x in fu if x]
        elif isinstance(fu, str):
            result["follow_up_considerations"] = [fu] if fu.strip() else []

        # Disclaimer
        disc = data.get("disclaimer")
        if isinstance(disc, str) and disc.strip():
            result["disclaimer"] = disc.strip()

        return result
