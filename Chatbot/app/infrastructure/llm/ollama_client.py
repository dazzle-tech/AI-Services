"""Ollama LLM client wrapper."""
import logging
from typing import Optional, Dict, Any
from ollama import Client as _OllamaClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class OllamaClient:
    """Wrapper for Ollama LLM client."""
    
    def __init__(self, host: Optional[str] = None, model: Optional[str] = None):
        self.host = host or settings.ollama_host
        self.model = model or settings.llm_model
        self._client = _OllamaClient(host=self.host)
    
    def generate(self, prompt: str, model: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate text using Ollama.
        
        Args:
            prompt: Input prompt
            model: Model name (overrides default)
            options: Generation options (temperature, num_ctx, etc.)
            
        Returns:
            Generated text response
        """
        model = model or self.model
        options = options or {"temperature": 0.1, "num_ctx": 4096}
        
        try:
            resp = self._client.generate(model=model, prompt=prompt, options=options)
            return (resp.get("response") or "").strip()
        except Exception as e:
            logger.warning(f"⚠️ Ollama failed: {e}")
            return ""
    
    def chat(self, prompt: str, session: Optional[Dict[str, Any]] = None) -> str:
        """
        Chat with local Ollama model (alias for generate for backward compatibility).
        
        Args:
            prompt: Input prompt
            session: Optional session context (currently unused but kept for compatibility)
            
        Returns:
            Generated text response
        """
        return self.generate(prompt)


# Global instance for backward compatibility
_ollama_client = OllamaClient()


def llama_chat(prompt: str, session: Optional[Dict[str, Any]] = None) -> str:
    """
    Legacy function for backward compatibility.
    
    Args:
        prompt: Input prompt
        session: Optional session context
        
    Returns:
        Generated text response
    """
    return _ollama_client.chat(prompt, session)



