"""Unit tests for Step 4: structured formatting of the caller-chosen document type."""
from unittest.mock import MagicMock

import pytest

from app.models.schemas import DocumentType
from app.services.formatting_service import FormattingService


@pytest.fixture
def ai_client_stub():
    return MagicMock()


@pytest.fixture
def service(ai_client_stub):
    return FormattingService(ai_client_stub)


class TestFormattingServiceLabResult:
    def test_classifies_and_formats_lab_result(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {
                "test_date": "2026-08-01",
                "ordering_provider": "Dr. Hassan",
                "results": [
                    {"test_name": "WBC", "value": "11.2", "unit": "10^9/L", "reference_range": "4.0-11.0", "flag": "high"},
                ],
            },
        }

        document_type, structured_data = service.format("lab text", DocumentType.LAB_RESULT)

        assert document_type == "lab_result"
        assert structured_data["test_date"] == "2026-08-01"
        assert structured_data["results"][0]["test_name"] == "WBC"
        assert structured_data["results"][0]["flag"] == "high"


class TestFormattingServiceRadiology:
    def test_classifies_and_formats_radiology_report(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {
                "study_date": "2026-07-20",
                "modality": "X-Ray",
                "body_part_examined": "Chest",
                "findings": "No acute process.",
                "impression": "Normal.",
            },
        }

        document_type, structured_data = service.format("radiology text", DocumentType.RADIOLOGY_REPORT)

        assert document_type == "radiology_report"
        assert structured_data["modality"] == "X-Ray"


class TestFormattingServicePrescription:
    def test_classifies_and_formats_prescription(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {
                "prescription_date": "2026-08-10",
                "prescribing_provider": "Dr. Hassan",
                "medications": [
                    {"name": "Amoxicillin", "dosage": "500mg", "frequency": "TID", "route": "oral", "duration": "7 days"},
                ],
            },
        }

        document_type, structured_data = service.format("prescription text", DocumentType.PRESCRIPTION)

        assert document_type == "prescription"
        assert structured_data["medications"][0]["name"] == "Amoxicillin"


class TestFormattingServiceClinicalNote:
    def test_classifies_and_formats_clinical_note(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {
                "note_date": "2026-08-15",
                "author": "Dr. Hassan",
                "subjective": "Headache.",
                "assessment": "Tension headache.",
            },
        }

        document_type, structured_data = service.format("note text", DocumentType.CLINICAL_NOTE)

        assert document_type == "clinical_note"
        assert structured_data["assessment"] == "Tension headache."


class TestFormattingServiceChosenType:
    def test_discharge_summary_keeps_generic_shape_and_chosen_type(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {
            "document_type": "lab_result",
            "extracted_fields": {"summary": "Discharged home."},
        }

        document_type, structured_data = service.format("summary text", DocumentType.DISCHARGE_SUMMARY)

        assert document_type == "discharge_summary"
        assert structured_data["document_type"] == "discharge_summary"
        assert structured_data["summary"] == "Discharged home."
        assert "summary text" in structured_data["content"]
        ai_client_stub.extract_fields.assert_called_once_with("summary text", "discharge_summary")

    def test_imaging_report_keeps_the_chosen_type(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {
            "extracted_fields": {"modality": "MRI", "impression": "Unremarkable."},
        }

        document_type, structured_data = service.format("scan text", DocumentType.IMAGING_REPORT)

        assert document_type == "imaging_report"
        assert structured_data["document_type"] == "imaging_report"
        assert structured_data["modality"] == "MRI"

    def test_missing_extracted_fields_does_not_crash(self, service, ai_client_stub):
        ai_client_stub.extract_fields.return_value = {"document_type": "prescription"}

        document_type, structured_data = service.format("text", DocumentType.LAB_RESULT)

        assert document_type == "lab_result"
        assert structured_data["document_type"] == "lab_result"
        assert structured_data["results"] == []
