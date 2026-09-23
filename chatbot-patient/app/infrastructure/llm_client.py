"""LLM client for the patient agent.

The implementation is ``medai_core.llm.client``, shared with the clinician bot. This
module binds it to the patient bot's settings and keeps ``get_llm_client()`` as the
single entry point the agent code uses.
"""
import logging
from typing import Optional

from medai_core.llm.client import OPENAI_AVAILABLE, LLMClient as _CoreLLMClient

from app.core.config import settings

logger = logging.getLogger(__name__)

__all__ = ["LLMClient", "get_llm_client", "OPENAI_AVAILABLE"]


class LLMClient(_CoreLLMClient):
    """Shared client, configured from the patient bot's settings."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        super().__init__(
            api_key=api_key or settings.openai_api_key,
            model=model or settings.openai_model,
            base_url=base_url if base_url is not None else settings.openai_base_url,
            timeout=settings.openai_timeout,
            max_retries=settings.openai_max_retries,
        )


_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
