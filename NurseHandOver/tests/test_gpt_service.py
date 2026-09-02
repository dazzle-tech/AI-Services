"""
test_gpt_service.py
-------------------
Tests for gpt_service.py — the OpenAI client is mocked throughout.
No real API calls are made in this test file.
"""

import pytest
import openai
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.gpt_service import call_gpt


SAMPLE_SYSTEM = "You are a clinical assistant."
SAMPLE_USER   = "Summarise this patient."
VALID_JSON    = '{"patient_id": "pt_001", "priority": "critical"}'


def _make_mock_response(content: str):
    """Builds a mock that matches the shape of openai.ChatCompletion response."""
    mock_message = MagicMock()
    mock_message.content = content

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


@pytest.mark.asyncio
async def test_successful_call_returns_string():
    """A clean API response should return the raw content string."""
    mock_response = _make_mock_response(VALID_JSON)

    with patch("app.services.gpt_service._client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        result = await call_gpt(SAMPLE_SYSTEM, SAMPLE_USER)

    assert result == VALID_JSON


@pytest.mark.asyncio
async def test_rate_limit_retries_and_succeeds():
    """Should retry on RateLimitError and succeed on second attempt."""
    mock_response = _make_mock_response(VALID_JSON)

    with patch("app.services.gpt_service._client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[openai.RateLimitError("rate limit", response=MagicMock(), body={}), mock_response]
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):  # skip actual sleep
            result = await call_gpt(SAMPLE_SYSTEM, SAMPLE_USER)

    assert result == VALID_JSON


@pytest.mark.asyncio
async def test_rate_limit_exhausts_retries_raises():
    """Should raise RuntimeError after all retries are exhausted."""
    with patch("app.services.gpt_service._client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.RateLimitError("rate limit", response=MagicMock(), body={})
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="Max retries exceeded"):
                await call_gpt(SAMPLE_SYSTEM, SAMPLE_USER)


@pytest.mark.asyncio
async def test_authentication_error_raises_immediately():
    """AuthenticationError should NOT be retried — raise immediately."""
    with patch("app.services.gpt_service._client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.AuthenticationError("bad key", response=MagicMock(), body={})
        )
        with pytest.raises(RuntimeError, match="authentication failed"):
            await call_gpt(SAMPLE_SYSTEM, SAMPLE_USER)


@pytest.mark.asyncio
async def test_generic_api_error_raises_immediately():
    """A generic OpenAI APIError should raise RuntimeError without retrying."""
    with patch("app.services.gpt_service._client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.APIError("server error", request=MagicMock(), body={})
        )
        with pytest.raises(RuntimeError, match="OpenAI API error"):
            await call_gpt(SAMPLE_SYSTEM, SAMPLE_USER)


@pytest.mark.asyncio
async def test_uses_correct_model_and_parameters():
    """Verifies the API call is made with the configured model and parameters."""
    mock_response = _make_mock_response(VALID_JSON)

    with patch("app.services.gpt_service._client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        await call_gpt(SAMPLE_SYSTEM, SAMPLE_USER)

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["messages"][0]["content"] == SAMPLE_SYSTEM
        assert call_kwargs["messages"][1]["role"] == "user"
        assert call_kwargs["response_format"] == {"type": "json_object"}
