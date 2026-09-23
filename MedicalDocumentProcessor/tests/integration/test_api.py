"""Integration tests for the /api/v1/process-document endpoint.

Patches the four AIClient pipeline-step methods (the service's only external
dependency boundary) and exercises the real extraction, normalization, and
formatting code for each scenario.
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app
from tests.fixtures.sample_data import (
    SAMPLE_LAB_RESULT_TEXT,
    SAMPLE_LAB_RESULT_TEXT_MALE,
    SAMPLE_OLD_LAB_RESULT_TEXT,
)


@pytest.fixture
def client():
    return TestClient(app)


def _upload(client, text: str, patient: dict, translate: bool = False, target_language: str | None = None):
    files = {"file": ("document.txt", text.encode("utf-8"), "text/plain")}
    data = {"patient": json.dumps(patient), "translate": str(translate).lower()}
    if target_language:
        data["target_language"] = target_language
    return client.post("/api/v1/process-document", files=files, data=data)


PATIENT_JANE = {"patient_id": "P-1001", "full_name": "Jane Doe", "sex": "female", "date_of_birth": "1980-05-14"}


class TestHealthAndRoot:
    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "Medical Document Processor" in response.json()["message"]

    def test_health_endpoint(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "medical-document-processor"
        assert data["provider"] == "openai"


class TestScenarioInvalidPatientMatch:
    """(a) invalid patient match."""

    @patch("app.ai.client.AIClient.validate_patient_match")
    def test_sex_mismatch_returns_invalid_with_reason(self, mock_validate, client):
        mock_validate.return_value = {
            "is_valid": True,  # LLM missed it -- deterministic guardrail must still catch it
            "extracted_patient_signals": {
                "full_name": "John Smith", "sex": "male", "date_of_birth": None, "patient_id": None,
            },
            "mismatches": [],
            "reason": None,
        }

        response = _upload(client, SAMPLE_LAB_RESULT_TEXT_MALE, PATIENT_JANE)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "invalid"
        assert data["reason"] is not None
        assert "sex" in data["reason"].lower()
        assert data["structured_data"] is None
        assert data["raw_extracted_text"]  # traceability text always present


class TestScenarioIrrelevantOldDocument:
    """(b) irrelevant old document."""

    @patch("app.ai.client.AIClient.classify_relevance")
    @patch("app.ai.client.AIClient.validate_patient_match")
    def test_old_lab_result_returns_irrelevant_with_reason(
        self, mock_validate, mock_relevance, client
    ):
        mock_validate.return_value = {
            "is_valid": True,
            "extracted_patient_signals": {"full_name": "Jane Doe", "sex": "female", "date_of_birth": "1980-05-14", "patient_id": None},
            "mismatches": [],
            "reason": None,
        }
        mock_relevance.return_value = {
            "apparent_document_type": "lab_result",
            "document_date": "2019-03-11",
            "is_relevant": False,
            "reason": "Blood test dated 2019-03-11 -- outside the 180-day relevance window for lab_result.",
        }

        response = _upload(client, SAMPLE_OLD_LAB_RESULT_TEXT, PATIENT_JANE)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "irrelevant"
        assert "2019-03-11" in data["reason"]
        assert data["structured_data"] is None


class TestScenarioValidRequiringTranslation:
    """(c) valid document requiring translation."""

    @patch("app.ai.client.AIClient.classify_and_extract")
    @patch("app.ai.client.AIClient.process_translation")
    @patch("app.ai.client.AIClient.classify_relevance")
    @patch("app.ai.client.AIClient.validate_patient_match")
    def test_translated_document_is_processed(
        self, mock_validate, mock_relevance, mock_translate, mock_classify, client
    ):
        mock_validate.return_value = {
            "is_valid": True,
            "extracted_patient_signals": {"full_name": "Jane Doe", "sex": "female", "date_of_birth": "1980-05-14", "patient_id": None},
            "mismatches": [],
            "reason": None,
        }
        mock_relevance.return_value = {
            "apparent_document_type": "clinical_note",
            "document_date": "2026-08-15",
            "is_relevant": True,
            "reason": "Recent note within the relevance window.",
        }
        mock_translate.return_value = {
            "detected_language": "fr",
            "translated_text": "CLINICAL NOTE (translated to English)...",
        }
        mock_classify.return_value = {
            "document_type": "clinical_note",
            "extracted_fields": {
                "note_date": "2026-08-15", "author": "Dr. Hassan",
                "subjective": "Headache.", "assessment": "Tension headache.",
            },
        }

        response = _upload(
            client, "NOTE CLINIQUE ... texte francais", PATIENT_JANE, translate=True, target_language="en"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert data["detected_language"] == "fr"
        assert data["translated"] is True
        assert data["document_type"] == "clinical_note"
        assert data["structured_data"]["assessment"] == "Tension headache."

        # The classification step should have run on the TRANSLATED text, not the original.
        classify_args = mock_classify.call_args[0]
        assert "translated to English" in classify_args[0]


class TestScenarioValidNotRequiringTranslation:
    """(d) valid document not requiring translation."""

    @patch("app.ai.client.AIClient.classify_and_extract")
    @patch("app.ai.client.AIClient.process_translation")
    @patch("app.ai.client.AIClient.classify_relevance")
    @patch("app.ai.client.AIClient.validate_patient_match")
    def test_english_document_is_processed_without_translation(
        self, mock_validate, mock_relevance, mock_translate, mock_classify, client
    ):
        mock_validate.return_value = {
            "is_valid": True,
            "extracted_patient_signals": {"full_name": "Jane Doe", "sex": "female", "date_of_birth": "1980-05-14", "patient_id": None},
            "mismatches": [],
            "reason": None,
        }
        mock_relevance.return_value = {
            "apparent_document_type": "lab_result",
            "document_date": "2026-08-01",
            "is_relevant": True,
            "reason": "Recent lab result within the relevance window.",
        }
        mock_translate.return_value = {"detected_language": "en", "translated_text": None}
        mock_classify.return_value = {
            "document_type": "lab_result",
            "extracted_fields": {
                "test_date": "2026-08-01", "ordering_provider": "Dr. Hassan",
                "results": [{"test_name": "WBC", "value": "11.2", "unit": "10^9/L", "reference_range": "4.0-11.0", "flag": "high"}],
            },
        }

        response = _upload(client, SAMPLE_LAB_RESULT_TEXT, PATIENT_JANE, translate=False)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert data["detected_language"] == "en"
        assert data["translated"] is False
        assert data["document_type"] == "lab_result"
        assert data["structured_data"]["results"][0]["test_name"] == "WBC"
        mock_translate.assert_called_once()


class TestRequestParsing:
    def test_invalid_patient_json_returns_400(self, client):
        files = {"file": ("document.txt", b"some text", "text/plain")}
        data = {"patient": "not valid json", "translate": "false"}
        response = client.post("/api/v1/process-document", files=files, data=data)
        assert response.status_code == 400

    def test_empty_file_returns_422(self, client):
        files = {"file": ("document.txt", b"", "text/plain")}
        data = {"patient": json.dumps(PATIENT_JANE), "translate": "false"}
        response = client.post("/api/v1/process-document", files=files, data=data)
        assert response.status_code == 422


class TestAPIDocumentation:
    def test_docs_endpoint(self, client):
        assert client.get("/docs").status_code == 200

    def test_openapi_schema(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "/api/v1/process-document" in schema["paths"]
        assert "/api/v1/health" in schema["paths"]
