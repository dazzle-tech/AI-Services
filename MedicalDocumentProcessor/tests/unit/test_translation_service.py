"""Unit tests for Step 3: language detection + conditional translation."""
from unittest.mock import MagicMock

import pytest

from app.services.translation_service import TranslationService


@pytest.fixture
def ai_client_stub():
    return MagicMock()


@pytest.fixture
def service(ai_client_stub):
    return TranslationService(ai_client_stub)


class TestTranslationService:
    def test_translate_false_records_language_but_does_not_translate(self, service, ai_client_stub):
        ai_client_stub.process_translation.return_value = {
            "detected_language": "fr",
            "translated_text": None,
        }

        outcome = service.process("texte francais", translate_requested=False, target_language="en")

        assert outcome.detected_language == "fr"
        assert outcome.translated is False
        assert outcome.translated_text is None

    def test_translate_true_and_different_language_translates(self, service, ai_client_stub):
        ai_client_stub.process_translation.return_value = {
            "detected_language": "fr",
            "translated_text": "English text",
        }

        outcome = service.process("texte francais", translate_requested=True, target_language="en")

        assert outcome.detected_language == "fr"
        assert outcome.translated is True
        assert outcome.translated_text == "English text"

    def test_translate_true_but_already_target_language_skips(self, service, ai_client_stub):
        ai_client_stub.process_translation.return_value = {
            "detected_language": "en",
            "translated_text": None,
        }

        outcome = service.process("english text", translate_requested=True, target_language="en")

        assert outcome.detected_language == "en"
        assert outcome.translated is False
        assert outcome.translated_text is None

    def test_model_ignoring_translate_false_is_overridden_deterministically(self, service, ai_client_stub):
        # Even if the model mistakenly returns translated_text, translated must stay
        # False when translation wasn't requested (deterministic guardrail).
        ai_client_stub.process_translation.return_value = {
            "detected_language": "fr",
            "translated_text": "Should not be used",
        }

        outcome = service.process("texte francais", translate_requested=False, target_language="en")

        assert outcome.translated is False
        assert outcome.translated_text is None
