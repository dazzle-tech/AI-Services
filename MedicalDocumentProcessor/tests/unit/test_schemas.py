"""Unit tests for Pydantic schemas."""
import pytest
from pydantic import ValidationError

from app.models.schemas import (
    DocumentType,
    PatientInfo,
    ProcessDocumentResponse,
)


class TestPatientInfo:
    def test_valid_patient(self):
        patient = PatientInfo(
            patient_id="P-1001", full_name="Jane Doe", sex="female", date_of_birth="1980-05-14"
        )
        assert patient.patient_id == "P-1001"
        assert patient.sex == "female"

    def test_empty_patient_allowed(self):
        patient = PatientInfo()
        assert patient.patient_id is None
        assert patient.sex is None

    def test_invalid_sex_rejected(self):
        with pytest.raises(ValidationError):
            PatientInfo(sex="unknown")

    def test_invalid_date_of_birth_rejected(self):
        with pytest.raises(ValidationError, match="ISO date"):
            PatientInfo(date_of_birth="14/05/1980")

    def test_valid_date_of_birth_normalized(self):
        patient = PatientInfo(date_of_birth="1980-05-14")
        assert patient.date_of_birth == "1980-05-14"


class TestDocumentType:
    def test_values_lists_all_members(self):
        values = DocumentType.values()
        assert "lab_result" in values
        assert "radiology_report" in values
        assert "prescription" in values
        assert "clinical_note" in values

    def test_coerce_known_value(self):
        assert DocumentType.coerce("lab_result") == DocumentType.LAB_RESULT

    def test_coerce_case_and_spacing_insensitive(self):
        assert DocumentType.coerce("Lab Result") == DocumentType.LAB_RESULT
        assert DocumentType.coerce("RADIOLOGY-REPORT") == DocumentType.RADIOLOGY_REPORT

    def test_coerce_unknown_falls_back_to_other(self):
        assert DocumentType.coerce("some_unrecognized_type") == DocumentType.OTHER

    def test_coerce_none_falls_back_to_other(self):
        assert DocumentType.coerce(None) == DocumentType.OTHER


class TestProcessDocumentResponse:
    def test_minimal_valid_response(self):
        response = ProcessDocumentResponse(status="invalid", reason="mismatch", raw_extracted_text="text")
        assert response.status == "invalid"
        assert response.translated is False
        assert response.structured_data is None
        assert response.processing_metadata == {}

    def test_processed_response_with_structured_data(self):
        response = ProcessDocumentResponse(
            status="processed",
            detected_language="en",
            translated=False,
            document_type="lab_result",
            structured_data={"document_type": "lab_result", "results": []},
            raw_extracted_text="text",
        )
        assert response.status == "processed"
        assert response.structured_data["document_type"] == "lab_result"

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            ProcessDocumentResponse(status="not_a_real_status", raw_extracted_text="")
