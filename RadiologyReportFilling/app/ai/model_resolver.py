from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)

_VISION_MODEL_HINTS = (
    "vision",
    "vl",
    "gemma3",
    "llava",
    "bakllava",
    "moondream",
    "minicpm",
    "qwen2.5vl",
    "qwen3-vl",
    "llama3.2-vision",
)
_NON_GENERATION_MODEL_HINTS = ("embed", "whisper", "tts", "stt", "moderation", "rerank")


def model_not_found(exc: Exception) -> bool:
    message = str(exc).lower()
    return "model" in message and "not found" in message


def choose_fallback_model(
    requested_model: str,
    available_model_ids: Iterable[str],
    *,
    require_vision: bool = False,
) -> str | None:
    requested = (requested_model or "").strip()
    available = [str(model_id).strip() for model_id in available_model_ids if str(model_id).strip()]
    if not available:
        return None
    if requested in available:
        return requested

    if require_vision:
        vision_candidates = [
            model_id
            for model_id in available
            if any(hint in model_id.lower() for hint in _VISION_MODEL_HINTS)
        ]
        if vision_candidates:
            return vision_candidates[0]

    generation_candidates = [
        model_id
        for model_id in available
        if not any(hint in model_id.lower() for hint in _NON_GENERATION_MODEL_HINTS)
    ]
    if generation_candidates:
        return generation_candidates[0]
    return available[0]


def resolve_fallback_model(
    client: object,
    requested_model: str,
    *,
    require_vision: bool = False,
) -> str | None:
    try:
        listing = client.models.list()  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unable to list backend models for fallback resolution: %s", exc)
        return None

    data = getattr(listing, "data", listing) or []
    available = [getattr(item, "id", None) for item in data]
    fallback = choose_fallback_model(
        requested_model,
        available,
        require_vision=require_vision,
    )
    if fallback and fallback != requested_model:
        logger.warning(
            "Configured model '%s' is unavailable; falling back to installed model '%s'.",
            requested_model,
            fallback,
        )
    return fallback
