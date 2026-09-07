"""OpenAI client for clinical summary generation - optimized for GPT-4."""
import json
import logging
import re
import time
from typing import Dict, Any, Optional, List
from openai import OpenAI
from openai import APIError, RateLimitError, APITimeoutError, APIConnectionError
from app.core.config import settings
from app.ai.prompts import build_summary_prompt, build_encounter_summary_prompt

logger = logging.getLogger(__name__)


class AIClient:
    """Client for interacting with OpenAI API - optimized for GPT-4."""
    
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
    
    def generate_summary(self, patient_data: Dict[str, Any]) -> str:
        """
        Generate a clinical summary from patient data using GPT-4.
        
        Args:
            patient_data: Dictionary containing patient information
            
        Returns:
            Generated clinical summary as a string
            
        Raises:
            ValueError: If summary generation fails after retries
            RateLimitError: If rate limit is exceeded
        """
        # Build prompt
        messages = build_summary_prompt(patient_data)
        
        # Retry logic for transient failures
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"OpenAI API call attempt {attempt + 1}/{self.max_retries}")
                prompt_length = len(json.dumps(messages, ensure_ascii=False))
                logger.info(
                    "Calling summary generation using model %s base_url=%s timeout=%ss prompt_length=%s",
                    self.model,
                    self.base_url,
                    self.timeout,
                    prompt_length,
                )
                
                # Call OpenAI API with GPT-4
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    timeout=self.timeout,
                )
                
                # Extract content
                content = response.choices[0].message.content

                if not content:
                    # If a model with hybrid reasoning (e.g. Qwen3 family)
                    # spends its entire max_tokens budget on the internal
                    # <think> block, content comes back empty even though
                    # the API call itself succeeded (HTTP 200). See
                    # app.ai.prompts._uses_qwen3_thinking_model / /no_think.
                    reasoning = getattr(response.choices[0].message, "reasoning_content", None) \
                        or getattr(response.choices[0].message, "reasoning", None)
                    if reasoning:
                        logger.error(
                            "Model '%s' returned only reasoning content and no "
                            "final answer (likely exhausted max_tokens=%s while "
                            "thinking). Reasoning preview: %.200s",
                            self.model, self.max_tokens, reasoning
                        )
                    raise ValueError(
                        f"Empty response from model '{self.model}' - the model may have "
                        f"exhausted max_tokens on internal reasoning before producing "
                        f"an answer; consider raising OPENAI_MAX_TOKENS"
                    )
                
                # NOTE: reliability depends on the configured model (see OPENAI_MODEL).
                # Small/local models are more prone to ignoring the fidelity
                # instructions in the system prompt (see find_hallucinated_numbers
                # in summarization_service.py for a post-hoc fabrication check).
                summary = self._clean_summary(content)
                
                if not summary:
                    logger.warning("Generated summary is empty")
                    summary = "Unable to generate clinical summary. Please check input data."
                
                # Log usage if enabled
                if settings.enable_usage_tracking:
                    usage = response.usage
                    logger.info(
                        f"Token usage - Prompt: {usage.prompt_tokens}, "
                        f"Completion: {usage.completion_tokens}, "
                        f"Total: {usage.total_tokens}"
                    )
                
                return summary
                
            except RateLimitError as e:
                last_exception = e
                wait_time = self.retry_delay * (2 ** attempt)  # Exponential backoff
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
                # Non-retryable API errors
                logger.error(f"OpenAI API error: {e}")
                raise ValueError(f"OpenAI API error: {str(e)}")
                
            except Exception as e:
                logger.error(f"Unexpected error in AI summary generation: {e}")
                raise ValueError(f"AI summary generation failed: {str(e)}")
        
        # If we get here, all retries failed
        raise ValueError(f"Failed to generate summary after {self.max_retries} attempts: {str(last_exception)}")

    def generate_from_messages(
        self,
        messages: List[Dict[str, str]],
        *,
        keep_paragraphs: bool = False,
    ) -> str:
        """Run chat completion for an already-built message list."""
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                prompt_length = len(json.dumps(messages, ensure_ascii=False))
                logger.info(
                    "Calling summary generation using model %s base_url=%s timeout=%ss prompt_length=%s",
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
                    raise ValueError(
                        f"Empty response from model '{self.model}' - the model may have "
                        f"exhausted max_tokens on internal reasoning before producing "
                        f"an answer; consider raising OPENAI_MAX_TOKENS"
                    )
                summary = self._clean_summary(content, keep_paragraphs=keep_paragraphs)
                if not summary:
                    summary = "Unable to generate clinical summary. Please check input data."
                if settings.enable_usage_tracking and response.usage:
                    usage = response.usage
                    logger.info(
                        f"Token usage - Prompt: {usage.prompt_tokens}, "
                        f"Completion: {usage.completion_tokens}, "
                        f"Total: {usage.total_tokens}"
                    )
                return summary
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
            except Exception as e:
                logger.error(f"Unexpected error in AI summary generation: {e}")
                raise ValueError(f"AI summary generation failed: {str(e)}")
        raise ValueError(f"Failed to generate summary after {self.max_retries} attempts: {str(last_exception)}")

    def generate_encounter_summary(
        self,
        *,
        context_type: str,
        purpose: str,
        detail_level: str,
        encounter_id: str,
        extra_prompt: Optional[str],
        encounter_data: Dict[str, Any],
    ) -> str:
        """Generate an encounter clinical-overview summary."""
        messages = build_encounter_summary_prompt(
            context_type=context_type,
            purpose=purpose,
            detail_level=detail_level,
            encounter_id=encounter_id,
            extra_prompt=extra_prompt,
            encounter_data=encounter_data,
        )
        return self.generate_from_messages(messages, keep_paragraphs=True)
    
    def _clean_summary(self, raw_output: str, *, keep_paragraphs: bool = False) -> str:
        """
        Clean and format the generated summary.
        Note: cleaning needs scale with model reliability - smaller/local
        models (see OPENAI_MODEL) may need more aggressive post-processing
        than a frontier model like GPT-4o would.
        """
        # Remove common prefixes that GPT-4 might add
        prefixes_to_remove = [
            "clinical summary:",
            "summary:",
            "here is the clinical summary:",
            "here's the clinical summary:",
            "clinical summary",
            "encounter summary:",
        ]
        
        cleaned = raw_output.strip()

        # Strip any leftover <think>...</think> reasoning block. Some
        # reasoning models/servers include the thinking block inline in
        # `content` alongside the real answer rather than omitting it -
        # /no_think in the prompt (see app.ai.prompts) should prevent this,
        # but we defend against it here too rather than surfacing raw
        # reasoning to callers.
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()
        
        # Remove prefixes (case-insensitive)
        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix):].strip()
                # Remove leading colon if present
                if cleaned.startswith(":"):
                    cleaned = cleaned[1:].strip()
        
        if keep_paragraphs:
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        else:
            # Remove any trailing meta-commentary
            lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
            if len(lines) > 1:
                # Take the first substantial (non-blank) line - usually the summary
                cleaned = lines[0]
            elif lines:
                cleaned = lines[0]
        
        # Ensure it's a complete sentence/paragraph
        if cleaned and not cleaned.endswith(('.', '!', '?')):
            # Add period if missing
            cleaned = cleaned.rstrip() + '.'
        
        return cleaned.strip()

