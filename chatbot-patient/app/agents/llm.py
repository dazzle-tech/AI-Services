"""Thin LLM helpers for the patient agent nodes."""
import logging
from typing import Optional

from medai_core.llm.json_utils import parse_json   # re-exported; shared with the clinician bot

from app.core.config import settings
from app.infrastructure.llm_client import get_llm_client

__all__ = ["complete", "stream", "complete_json", "parse_json", "FAST_MODEL", "ANSWER_MODEL"]

logger = logging.getLogger(__name__)

# Model tiering, same idea as the clinician bot: routing/classification on the cheap
# fast model, user-facing prose on the stronger one.
FAST_MODEL = settings.openai_model
ANSWER_MODEL = settings.reasoning_model


def complete(system: str, user: str = "", *, temperature: float = 0.2,
             max_tokens: int = 800, model: Optional[str] = None) -> str:
    prompt = f"{system}\n\n{user}".strip() if user else system
    try:
        return get_llm_client().generate(
            prompt, model=model or FAST_MODEL,
            options={"temperature": temperature, "max_tokens": max_tokens},
        ) or ""
    except Exception as exc:      # never raise into the graph
        logger.warning("LLM completion failed: %s", exc)
        return ""


def stream(system: str, user: str = "", *, temperature: float = 0.3,
           max_tokens: int = 700, model: Optional[str] = None):
    prompt = f"{system}\n\n{user}".strip() if user else system
    try:
        yield from get_llm_client().stream(
            prompt, model=model or ANSWER_MODEL,
            options={"temperature": temperature, "max_tokens": max_tokens},
        )
    except Exception as exc:      # never raise into the endpoint
        logger.warning("LLM stream failed: %s", exc)


def complete_json(system: str, user: str = "", **kwargs) -> Optional[dict]:
    return parse_json(complete(system, user, **kwargs))
