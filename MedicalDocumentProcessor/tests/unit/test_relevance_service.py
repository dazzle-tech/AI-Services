"""Unit tests for Step 2: relevance check."""
from datetime import date, timedelta
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
            "document_date": (date.today() - timedelta(days=30)).isoformat(),
            "is_relevant": True,
            "reason": "Recent lab result within the relevance window.",
        }

        outcome = service.check("recent lab text", [], "lab_result")

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

        outcome = service.check("old lab text", [], "lab_result")

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

        outcome = service.check("text", [], "prescription")

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

        outcome = service.check("text", existing, "lab_result")

        ai_client_stub.classify_relevance.assert_called_once()
        _, _, forwarded_existing, forwarded_type = ai_client_stub.classify_relevance.call_args[0]
        assert forwarded_existing == [{"document_type": "lab_result", "document_date": "2026-08-05"}]
        assert forwarded_type == "lab_result"
        assert outcome.is_relevant is False

    def test_old_date_is_irrelevant_even_when_the_model_accepts_it(self, service, ai_client_stub):
        ai_client_stub.classify_relevance.return_value = {
            "document_date": "2019-03-11",
            "is_relevant": True,
            "reason": "Accepted.",
        }

        outcome = service.check("Test Date: 2019-03-11", [], "lab_result")

        assert outcome.is_relevant is False
        assert outcome.document_date == "2019-03-11"
        assert "180-day" in outcome.reason

    def test_printed_test_date_overrides_a_newer_model_date(self, service, ai_client_stub):
        ai_client_stub.classify_relevance.return_value = {
            "document_date": date.today().isoformat(),
            "is_relevant": True,
            "reason": "Recent.",
        }
        text = "Date of Birth: 1980-05-14\nTest Date: 2019-03-11\n"

        outcome = service.check(text, [], "radiology_report")

        assert outcome.is_relevant is False
        assert outcome.document_date == "2019-03-11"
        assert "365-day" in outcome.reason

    def test_date_of_birth_alone_does_not_make_a_document_irrelevant(self, service, ai_client_stub):
        ai_client_stub.classify_relevance.return_value = {
            "document_date": None,
            "is_relevant": True,
            "reason": "No clinical date.",
        }

        outcome = service.check("Date of Birth: 1980-05-14", [], "lab_result")

        assert outcome.is_relevant is True
