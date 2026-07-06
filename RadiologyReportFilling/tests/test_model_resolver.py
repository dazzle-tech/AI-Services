import os

from app.ai.model_resolver import choose_fallback_model


REQUESTED_MODEL = os.getenv("OPENAI_MODEL", "") or "configured-model"


def test_choose_fallback_model_returns_requested_when_available() -> None:
    assert choose_fallback_model(REQUESTED_MODEL, [REQUESTED_MODEL, "gemma3:4b"]) == REQUESTED_MODEL


def test_choose_fallback_model_skips_embedding_models_for_text() -> None:
    assert choose_fallback_model("missing-model", ["nomic-embed-text", "gemma3:4b"]) == "gemma3:4b"


def test_choose_fallback_model_prefers_vision_capable_models() -> None:
    assert (
        choose_fallback_model(
            "missing-vision-model",
            ["nomic-embed-text", "gemma3:4b", "llama3.2:3b"],
            require_vision=True,
        )
        == "gemma3:4b"
    )
