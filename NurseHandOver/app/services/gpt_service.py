"""
gpt_service.py
--------------
Handles all communication with the LLM endpoint.

Keeping this isolated means:
- Swapping the model only touches this file.
- Retry logic, timeouts, and API-level error handling live in one place.
- Unit tests can mock this module without touching prompt or parsing logic.

Points at the SHARED OpenAI-compatible endpoint configured for the whole stack
(OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL).
"""

import asyncio
import openai
from openai import AsyncOpenAI

from app.core.config import settings

# Single shared client instance (thread-safe, connection-pooled)
_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url or None,
)


async def call_gpt(system_prompt: str, user_prompt: str) -> str:
    """
    Sends a chat completion request and returns the raw response string.

    - Uses response_format=json_object to guarantee valid JSON output.
    - Retries on rate limit errors with exponential backoff.
    - Raises RuntimeError on non-retriable failures so callers can handle gracefully.

    Returns:
        Raw JSON string from the model (not yet parsed or validated).
    """
    last_error: Exception | None = None

    for attempt in range(settings.max_retries + 1):
        try:
            response = await _client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                response_format={"type": "json_object"},  # enforce valid JSON at the protocol level
            )
            return response.choices[0].message.content

        except openai.RateLimitError as e:
            last_error = e
            if attempt < settings.max_retries:
                wait = 2 ** attempt  # 1s, 2s, 4s ...
                await asyncio.sleep(wait)

        except openai.AuthenticationError as e:
            # No point retrying — bad API key
            raise RuntimeError("LLM authentication failed. Check OPENAI_API_KEY.") from e

        except openai.APIError as e:
            # Generic API error — raise immediately
            raise RuntimeError(f"LLM API error: {e}") from e

    raise RuntimeError(
        f"GPT call failed after {settings.max_retries + 1} attempts. Last error: {last_error}"
    )
