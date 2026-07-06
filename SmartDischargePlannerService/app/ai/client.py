"""OpenAI client for discharge planning assessment."""
import json
import logging
import re
import time
from typing import Dict, Any, Optional
from openai import OpenAI
from openai import APIError, RateLimitError, APITimeoutError, APIConnectionError
from app.core.config import settings
from app.ai.prompts import build_discharge_prompt

logger = logging.getLogger(__name__)

# Expected keys for discharge plan JSON
DISCHARGE_PLAN_KEYS = {
    "readiness_status",
    "readiness_reason",
    "blockers",
    "medication_reconciliation_concerns",
    "follow_up_considerations",
    "draft_discharge_summary",
    "disclaimer",
}


def _normalize_discharge_output(raw: str) -> Dict[str, Any]:
    """
    Parse and normalize LLM output to a valid discharge plan dict.
    Handles markdown code blocks and minor formatting issues.
    """
    cleaned = raw.strip()
    
    # Remove markdown code blocks if present
    code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if code_block_match:
        cleaned = code_block_match.group(1).strip()
    
    # Try to parse JSON
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to extract JSON object with regex
        obj_match = re.search(r"\{[\s\S]*\}", cleaned)
        if obj_match:
            try:
                parsed = json.loads(obj_match.group(0))
            except json.JSONDecodeError:
                raise ValueError("Could not parse AI response as valid JSON")
        else:
            raise ValueError("Could not parse AI response as valid JSON")
    
    if not isinstance(parsed, dict):
        raise ValueError("AI response must be a JSON object")
    
    # Ensure required keys exist with defaults
    result = {
        "readiness_status": parsed.get("readiness_status", "unclear"),
        "readiness_reason": parsed.get("readiness_reason", "Unable to assess."),
        "blockers": parsed.get("blockers", []),
        "medication_reconciliation_concerns": parsed.get("medication_reconciliation_concerns", []),
        "follow_up_considerations": parsed.get("follow_up_considerations", []),
        "draft_discharge_summary": parsed.get("draft_discharge_summary", ""),
        "disclaimer": parsed.get(
            "disclaimer",
            "This output supports discharge planning and does not replace clinician judgment."
        ),
    }
    
    # Normalize blockers to {category, title, reason}
    normalized_blockers = []
    for b in result["blockers"]:
        if isinstance(b, dict):
            normalized_blockers.append({
                "category": b.get("category", "other"),
                "title": b.get("title", str(b)),
                "reason": b.get("reason", ""),
            })
        else:
            normalized_blockers.append({"category": "other", "title": str(b), "reason": ""})
    result["blockers"] = normalized_blockers
    
    # Ensure lists
    if not isinstance(result["medication_reconciliation_concerns"], list):
        result["medication_reconciliation_concerns"] = []
    if not isinstance(result["follow_up_considerations"], list):
        result["follow_up_considerations"] = []
    
    return result


class AIClient:
    """Client for interacting with OpenAI API for discharge planning."""
    
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
    
    def plan_discharge(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate discharge planning assessment from clinical and operational data.
        
        Args:
            input_data: Dict with patient_context, clinical_data, operational_data
            
        Returns:
            Parsed discharge plan dict with readiness_status, blockers, etc.
        """
        messages = build_discharge_prompt(input_data)
        
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"OpenAI API call attempt {attempt + 1}/{self.max_retries}")
                prompt_length = len(json.dumps(messages, ensure_ascii=False))
                logger.info(
                    "Calling discharge planning using model %s base_url=%s timeout=%ss prompt_length=%s",
                    self.model,
                    self.base_url,
                    self.timeout,
                    prompt_length,
                )
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    timeout=self.timeout,
                )
                
                content = response.choices[0].message.content
                
                if not content:
                    raise ValueError("Empty response from model")
                
                plan = _normalize_discharge_output(content)
                
                if settings.enable_usage_tracking:
                    usage = response.usage
                    logger.info(
                        f"Token usage - Prompt: {usage.prompt_tokens}, "
                        f"Completion: {usage.completion_tokens}, "
                        f"Total: {usage.total_tokens}"
                    )
                
                return plan
                
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
                if "Could not parse" in str(e) or "Empty response" in str(e):
                    last_exception = e
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                raise
                
            except Exception as e:
                logger.error(f"Unexpected error in AI discharge planning: {e}")
                raise ValueError(f"AI discharge planning failed: {str(e)}")
        
        raise ValueError(f"Failed after {self.max_retries} attempts: {str(last_exception)}")
