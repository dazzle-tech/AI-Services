"""JSON repair and temperature fallback. The OpenAI HTTP call is replaced."""
import httpx
import pytest
from openai import APIError

from app.ai.client import AIClient
from app.core.config import settings
from tests.fixtures.scripted_model import completion


def _temperature_error():
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return APIError(
        "Unsupported parameter: 'temperature' is not supported with this model.",
        request=request,
        body=None,
    )


def _install(monkeypatch, create):
    client = AIClient()
    client.max_retries = 2
    monkeypatch.setattr(client._completions, "create", create)
    return client


def test_malformed_json_is_retried_and_repaired(monkeypatch):
    """Two invalid payloads are followed by one repair call that validates."""
    calls = {"count": 0}

    def create(**kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            return completion("this is not json")
        user = kwargs["messages"][-1]["content"]
        assert "not valid JSON" in user
        return completion(
            {
                "events": [
                    {
                        "date": "2020-01-01",
                        "event_type": "allergy",
                        "title": "Penicillin allergy",
                        "description": "Penicillin allergy recorded.",
                        "clinical_importance": "high",
                        "source": "allergies",
                    }
                ]
            }
        )

    client = _install(monkeypatch, create)
    events = client.generate_timeline({"patient_id": "pt-1"})
    assert calls["count"] == 3
    assert events[0].title == "Penicillin allergy"
    assert events[0].event_type == "allergy"


def test_fenced_json_and_trailing_commas_parse_without_a_second_call(monkeypatch):
    """Fences and a trailing comma are repaired locally."""
    calls = {"count": 0}

    def create(**kwargs):
        calls["count"] += 1
        return completion(
            '```json\n{"clinical_summary": "Problem list. Hypertension diagnosed on 2021-03-10.",}\n```'
        )

    client = _install(monkeypatch, create)
    summary = client.generate_summary([], age=None, gender=None)
    assert calls["count"] == 1
    assert summary.startswith("Problem list.")


def test_temperature_is_omitted_when_the_model_rejects_it(monkeypatch):
    """A low temperature is sent, then dropped for a model that does not allow it."""
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            assert kwargs["temperature"] == settings.openai_temperature
            raise _temperature_error()
        assert "temperature" not in kwargs
        assert kwargs["model"] == settings.openai_model
        return completion({"events": []})

    client = _install(monkeypatch, create)
    assert client.generate_timeline({"patient_id": "pt-1"}) == []
    assert len(calls) == 2


def test_settings_require_a_configured_model_and_default_to_low_temperature():
    """The model name comes from the environment. Temperature defaults to zero."""
    assert settings.model_fields["openai_model"].is_required()
    assert settings.model_fields["openai_temperature"].default == 0.0
    assert settings.model_fields["api_port"].default == 8040
    assert settings.openai_model
    assert settings.openai_temperature <= 0.2


def test_repair_failure_raises_without_calling_the_network_again(monkeypatch):
    """A repair that is still not JSON becomes a client error."""
    client = _install(monkeypatch, lambda **kwargs: completion("still not json"))
    with pytest.raises(ValueError, match="Malformed model JSON"):
        client.generate_timeline({"patient_id": "pt-1"})
