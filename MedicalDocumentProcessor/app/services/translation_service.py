"""Step 3: language detection + conditional translation."""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.ai.client import AIClient
from app.models.schemas import TranslationOutcome

logger = logging.getLogger(__name__)


class TranslationService:
    def __init__(self, ai_client: AIClient) -> None:
        self.ai_client = ai_client

    def process(
        self, extracted_text: str, translate_requested: bool, target_language: str
    ) -> TranslationOutcome:
        raw = self.ai_client.process_translation(extracted_text, translate_requested, target_language)
        return self._normalize(raw, translate_requested, target_language)

    def _normalize(
        self, raw: Dict[str, Any], translate_requested: bool, target_language: str
    ) -> TranslationOutcome:
        detected_language = self._text(raw.get("detected_language")) or "unknown"
        translated_text = self._text(raw.get("translated_text"))

        # Deterministic guardrail: never report `translated=True` unless translation was
        # actually requested, matching Step 3's spec exactly regardless of model output.
        translated = bool(translate_requested and translated_text)

        return TranslationOutcome(
            detected_language=detected_language.lower(),
            translated=translated,
            translated_text=translated_text if translated else None,
        )

    @staticmethod
    def _text(value: Any):
        if value is None:
            return None
        text = str(value).strip()
        return text or None
