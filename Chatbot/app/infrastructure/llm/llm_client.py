"""
Unified LLM client that supports both Ollama and OpenAI.

This allows easy switching between local Ollama models and cloud-based OpenAI models
by setting the LLM_PROVIDER environment variable.
"""
import logging
from typing import Optional, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Unified LLM client that abstracts over Ollama and OpenAI.
    
    Usage:
        # Use Ollama (default)
        client = LLMClient()
        
        # Use OpenAI
        client = LLMClient(provider="openai")
        
        # Or set LLM_PROVIDER=openai environment variable
    """
    
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize LLM client.
        
        Args:
            provider: "ollama" or "openai" (defaults to LLM_PROVIDER env var or "ollama")
            model: Model name (overrides default for the provider)
        """
        self.provider = provider or settings.llm_provider
        self.model = model
        
        if self.provider == "openai":
            from app.infrastructure.llm.openai_client import OpenAIClient
            self._client = OpenAIClient(model=model)
            logger.info(f"✅ Using OpenAI provider with model: {self._client.model}")
        else:
            from app.infrastructure.llm.ollama_client import OllamaClient
            self._client = OllamaClient(model=model)
            logger.info(f"✅ Using Ollama provider with model: {self._client.model}")
    
    def generate(self, prompt: str, model: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> str:
        """Generate text using the configured provider."""
        return self._client.generate(prompt, model=model, options=options)
    
    def chat(self, prompt: str, session: Optional[Dict[str, Any]] = None) -> str:
        """Chat with the configured provider."""
        return self._client.chat(prompt, session)


# Global instance (lazy initialization)
_llm_client: Optional[LLMClient] = None


def get_llm_client(provider: Optional[str] = None, model: Optional[str] = None) -> LLMClient:
    """Get or create global LLM client instance."""
    global _llm_client
    if _llm_client is None or provider is not None:
        _llm_client = LLMClient(provider=provider, model=model)
    return _llm_client


