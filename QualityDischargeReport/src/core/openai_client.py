"""OpenAI API client wrapper."""

import os
import logging
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class OpenAIClient:
    """Wrapper for OpenAI API calls."""
    
    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        """Initialize OpenAI client.
        
        Args:
            model: Model name (defaults to OPENAI_MODEL env var)
            api_key: API key (defaults to OPENAI_API_KEY env var)
        """
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1") or None
        timeout = float(os.getenv("OPENAI_TIMEOUT", "120"))
        max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "1"))
        
        if not api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")
        
        self.base_url = base_url
        self.timeout = timeout
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)
    
    def complete(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4000
    ) -> str:
        """Complete a prompt using OpenAI API.
        
        Args:
            prompt: User prompt text
            system_message: Optional system message
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens in response
            
        Returns:
            Response text
        """
        messages = []
        
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        messages.append({"role": "user", "content": prompt})
        
        try:
            prompt_length = sum(len(message.get("content", "")) for message in messages if isinstance(message.get("content"), str))
            logger.info(
                "Calling quality discharge report using model %s base_url=%s timeout=%ss prompt_length=%s",
                self.model,
                self.base_url,
                self.timeout,
                prompt_length,
            )
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self.timeout,
            )
            
            content = response.choices[0].message.content
            if not content:
                reasoning = (
                    getattr(response.choices[0].message, "reasoning_content", None)
                    or getattr(response.choices[0].message, "reasoning", None)
                )
                if reasoning:
                    logger.error(
                        "Model '%s' returned only reasoning content and no final answer "
                        "(likely exhausted max_tokens=%s while thinking). Reasoning preview: %.200s",
                        self.model,
                        max_tokens,
                        reasoning,
                    )
                raise RuntimeError(
                    f"Empty response from model '{self.model}' - the model may have "
                    f"exhausted max_tokens on internal reasoning before producing an answer"
                )
            return content
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {str(e)}")

