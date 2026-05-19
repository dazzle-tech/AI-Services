"""OpenAI client for nursing task prioritization."""
import json
import logging
import re
import time
from typing import Dict, Any, List
from openai import OpenAI
from openai import APIError, RateLimitError, APITimeoutError, APIConnectionError
from app.core.config import settings
from app.ai.prompts import build_prioritization_prompt

logger = logging.getLogger(__name__)


class AIClient:
    """Client for interacting with OpenAI API for task prioritization."""

    def __init__(self):
        """Initialize OpenAI client."""
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set")
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.openai_timeout
        )
        self.model = settings.openai_model
        self.temperature = settings.openai_temperature
        self.max_tokens = settings.openai_max_tokens
        self.max_retries = settings.openai_max_retries
        self.retry_delay = settings.openai_retry_delay

    def prioritize_tasks(self, request_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Prioritize nursing tasks using the LLM.

        Args:
            request_data: Dictionary containing unit context, nurse context, and patients

        Returns:
            List of prioritized task dictionaries

        Raises:
            ValueError: If prioritization fails after retries
        """
        messages = build_prioritization_prompt(request_data)

        last_exception = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"OpenAI API call attempt {attempt + 1}/{self.max_retries}")

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    timeout=settings.openai_timeout
                )

                content = response.choices[0].message.content

                if not content:
                    raise ValueError("Empty response from model")

                tasks = self._parse_and_validate_output(content)

                if settings.enable_usage_tracking:
                    usage = response.usage
                    logger.info(
                        f"Token usage - Prompt: {usage.prompt_tokens}, "
                        f"Completion: {usage.completion_tokens}, "
                        f"Total: {usage.total_tokens}"
                    )

                return tasks

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
                    raise ValueError(f"API connection failed after {self.max_retries} attempts: {str(e)}")

            except APIError as e:
                logger.error(f"OpenAI API error: {e}")
                raise ValueError(f"OpenAI API error: {str(e)}")

            except ValueError as e:
                if "Empty response" in str(e) or "Failed to parse" in str(e):
                    last_exception = e
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
                        continue
                raise

            except Exception as e:
                logger.error(f"Unexpected error in AI prioritization: {e}")
                raise ValueError(f"AI prioritization failed: {str(e)}")

        raise ValueError(f"Failed to prioritize tasks after {self.max_retries} attempts: {str(last_exception)}")

    def _parse_and_validate_output(self, raw_output: str) -> List[Dict[str, Any]]:
        """
        Parse and validate LLM output. Handles markdown code blocks and malformed JSON.
        """
        cleaned = raw_output.strip()

        # Remove markdown code blocks if present
        if "```" in cleaned:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
            if match:
                cleaned = match.group(1).strip()

        # Try to extract JSON array
        start = cleaned.find("[")
        if start >= 0:
            depth = 0
            end = -1
            for i, c in enumerate(cleaned[start:], start):
                if c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end >= 0:
                json_str = cleaned[start:end + 1]
                try:
                    data = json.loads(json_str)
                    if isinstance(data, list):
                        return self._normalize_tasks(data)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse error: {e}")

        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return self._normalize_tasks(data)
        except json.JSONDecodeError:
            pass

        raise ValueError("Failed to parse prioritization output: no valid JSON array found")

    def _normalize_tasks(self, raw_tasks: List[Any]) -> List[Dict[str, Any]]:
        """Normalize and validate task objects."""
        normalized = []
        required = {"rank", "patient_id", "room", "task_id", "task_type", "title", "reason", "urgency", "recommended_timeframe", "source_signals"}

        for i, t in enumerate(raw_tasks):
            if not isinstance(t, dict):
                continue
            task = {k: v for k, v in t.items()}
            task.setdefault("rank", i + 1)
            task.setdefault("patient_id", "")
            task.setdefault("room", "")
            task.setdefault("task_id", "")
            task.setdefault("task_type", "nursing_task")
            task.setdefault("title", "")
            task.setdefault("reason", "")
            task.setdefault("urgency", "medium")
            task.setdefault("recommended_timeframe", "as_able")
            task.setdefault("source_signals", [] if isinstance(task.get("source_signals"), list) else [])
            if not isinstance(task["source_signals"], list):
                task["source_signals"] = []
            normalized.append(task)

        return normalized
