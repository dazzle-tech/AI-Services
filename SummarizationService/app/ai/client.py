"""OpenAI client for clinical summary generation - optimized for GPT-4."""
import json
import logging
import time
from typing import Dict, Any, Optional
from openai import OpenAI
from openai import APIError, RateLimitError, APITimeoutError, APIConnectionError
from app.core.config import settings
from app.ai.prompts import build_summary_prompt

logger = logging.getLogger(__name__)


class AIClient:
    """Client for interacting with OpenAI API - optimized for GPT-4."""
    
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
                
                # Call OpenAI API with GPT-4
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    timeout=settings.openai_timeout
                )
                
                # Extract content
                content = response.choices[0].message.content
                
                if not content:
                    raise ValueError("Empty response from GPT-4 model")
                
                # GPT-4 is reliable, minimal cleaning needed
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
    
    def _clean_summary(self, raw_output: str) -> str:
        """
        Clean and format the generated summary.
        GPT-4 is generally reliable, so minimal cleaning is needed.
        """
        # Remove common prefixes that GPT-4 might add
        prefixes_to_remove = [
            "clinical summary:",
            "summary:",
            "here is the clinical summary:",
            "here's the clinical summary:",
            "clinical summary",
        ]
        
        cleaned = raw_output.strip()
        
        # Remove prefixes (case-insensitive)
        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix):].strip()
                # Remove leading colon if present
                if cleaned.startswith(":"):
                    cleaned = cleaned[1:].strip()
        
        # Remove any trailing meta-commentary
        lines = cleaned.splitlines()
        if len(lines) > 1:
            # Take the first substantial line (usually the summary)
            cleaned = lines[0].strip()
        
        # Ensure it's a complete sentence/paragraph
        if cleaned and not cleaned.endswith(('.', '!', '?')):
            # Add period if missing
            cleaned = cleaned.rstrip() + '.'
        
        return cleaned.strip()

