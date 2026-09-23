"""Unit tests for Step 2: relevance check."""
from unittest.mock import MagicMock

import pytest

from app.services.relevance_service import RelevanceService


@pytest.fixture
def ai_client_stub():
    return MagicMock()


@pytest.fixture
def service(ai_client_stub):
    return RelevanceService(ai_client_stub)


class TestRelevanceService:
    def test_recent_document_is_relevant(self, service, ai_client_stub):
        ai_client_stub.classify_relevance.return_value = {
            "apparent_document_type": "lab_result",
            "document_date": "2026-08-01",
            "is_relevant": True,
            "reason": "Recent lab result within the relevance window.",
        }

        outcome = service.check("recent lab text", [])

        assert outcome.is_relevant is True
        assert outcome.apparent_document_type == "lab_result"
        assert outcome.relevance_window_days == 180

    def test_old_document_is_irrelevant_with_specific_reason(self, service, ai_client_stub):
        ai_client_stub.classify_relevance.return_value = {
            "apparent_document_type": "lab_result",
            "document_date": "2019-03-11",
            "is_relevant": False,
            "reason": "Blood test dated 2019-03-11 -- outside the 180-day relevance window for lab_result.",
        }

        outcome = service.check("old lab text", [])

        assert outcome.is_relevant is False
        assert "2019-03-11" in outcome.reason
        assert outcome.relevance_window_days == 180

    def test_missing_reason_gets_a_default(self, service, ai_client_stub):
        ai_client_stub.classify_relevance.return_value = {
            "apparent_document_type": "prescription",
            "document_date": None,
            "is_relevant": False,
            "reason": None,
        }

        outcome = service.check("text", [])

        assert outcome.is_relevant is False
        assert outcome.reason  # non-empty default reason

    def test_existing_documents_are_forwarded_to_ai_client(self, service, ai_client_stub):
        from app.models.schemas import ExistingDocumentSummary

        ai_client_stub.classify_relevance.return_value = {
            "apparent_document_type": "lab_result",
            "document_date": "2026-07-01",
            "is_relevant": False,
            "reason": "Superseded by a newer lab result already on record.",
        }
        existing = [ExistingDocumentSummary(document_type="lab_result", document_date="2026-08-05")]

        outcome = service.check("text", existing)

        ai_client_stub.classify_relevance.assert_called_once()
        _, _, forwarded_existing = ai_client_stub.classify_relevance.call_args[0]
        assert forwarded_existing == [{"document_type": "lab_result", "document_date": "2026-08-05"}]
        assert outcome.is_relevant is False
