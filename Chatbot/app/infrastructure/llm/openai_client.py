"""OpenAI LLM client wrapper for GPT-4o and other OpenAI models."""
import logging
from typing import Optional, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

# Try to import openai, but handle gracefully if not available
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("⚠️ OpenAI library not installed. Install with: pip install openai")


class OpenAIClient:
    """Wrapper for OpenAI API client."""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: Model name (defaults to openai_model from settings)
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI library not installed. Install with: pip install openai")
        
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        self.base_url = settings.openai_base_url
        self.timeout = settings.openai_timeout
        self.max_retries = settings.openai_max_retries
        
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")
        
        self._client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url or None,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )
    
    def generate(self, prompt: str, model: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate text using OpenAI API.
        
        Args:
            prompt: Input prompt
            model: Model name (overrides default)
            options: Generation options (temperature, etc.)
            
        Returns:
            Generated text response
        """
        model = model or self.model
        options = options or {"temperature": 0.1}
        
        try:
            prompt_length = len(prompt)
            logger.info(
                "Calling chatbot OpenAI client using model %s base_url=%s timeout=%ss prompt_length=%s",
                model,
                self.base_url,
                self.timeout,
                prompt_length,
            )
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=options.get("temperature", 0.1),
                timeout=self.timeout,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.error(f"❌ OpenAI API error: {e}")
            return ""
    
    def chat(self, prompt: str, session: Optional[Dict[str, Any]] = None) -> str:
        """
        Chat with OpenAI model (alias for generate for backward compatibility).
        
        Args:
            prompt: Input prompt
            session: Optional session context (currently unused but kept for compatibility)
            
        Returns:
            Generated text response
        """
        return self.generate(prompt)


# Global instance (lazy initialization)
_openai_client: Optional[OpenAIClient] = None


def get_openai_client() -> OpenAIClient:
    """Get or create global OpenAI client instance."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAIClient()
    return _openai_client


