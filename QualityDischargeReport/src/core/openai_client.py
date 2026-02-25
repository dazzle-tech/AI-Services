"""OpenAI API client wrapper."""

import os
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class OpenAIClient:
    """Wrapper for OpenAI API calls."""
    
    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        """Initialize OpenAI client.
        
        Args:
            model: Model name (defaults to OPENAI_MODEL env var)
            api_key: API key (defaults to OPENAI_API_KEY env var)
        """
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1")
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")
        
        self.client = OpenAI(api_key=api_key)
    
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {str(e)}")

