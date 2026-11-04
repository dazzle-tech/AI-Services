"""Unit tests for Step 1: patient-match validation."""
from unittest.mock import MagicMock

import pytest

from app.services.validation_service import ValidationService
from tests.fixtures.sample_data import SAMPLE_PATIENT, SAMPLE_PATIENT_MALE


@pytest.fixture
def ai_client_stub():
    return MagicMock()


@pytest.fixture
def service(ai_client_stub):
    return ValidationService(ai_client_stub)


class TestValidationService:
    def test_matching_patient_is_valid(self, service, ai_client_stub):
        ai_client_stub.validate_patient_match.return_value = {
            "is_valid": True,
            "extracted_patient_signals": {
                "full_name": "Jane Doe",
                "sex": "female",
                "date_of_birth": "1980-05-14",
                "patient_id": None,
            },
            "mismatches": [],
            "reason": None,
        }

        outcome = service.validate(SAMPLE_PATIENT, "text mentioning Jane Doe")

        assert outcome.is_valid is True
        assert outcome.reason is None
        assert outcome.extracted_patient_signals["sex"] == "female"

    def test_llm_flagged_mismatch_is_invalid(self, service, ai_client_stub):
        ai_client_stub.validate_patient_match.return_value = {
            "is_valid": False,
            "extracted_patient_signals": {"full_name": "Someone Else", "sex": None, "date_of_birth": None, "patient_id": None},
            "mismatches": ["Document name 'Someone Else' does not match patient record 'Jane Doe'"],
            "reason": "Name mismatch",
        }

        outcome = service.validate(SAMPLE_PATIENT, "text about Someone Else")

        assert outcome.is_valid is False
        assert "Someone Else" in outcome.reason
        assert [item.model_dump() for item in outcome.mismatch_details] == [
            {
                "field": "full_name",
                "patient_record_value": "Jane Doe",
                "document_value": "Someone Else",
            }
        ]

    def test_deterministic_sex_mismatch_overrides_llm_valid_flag(self, service, ai_client_stub):
        # LLM incorrectly says valid, but the document clearly states a different sex.
        ai_client_stub.validate_patient_match.return_value = {
            "is_valid": True,
            "extracted_patient_signals": {
                "full_name": "Jane Doe", "sex": "male", "date_of_birth": None, "patient_id": None,
            },
            "mismatches": [],
            "reason": None,
        }

        outcome = service.validate(SAMPLE_PATIENT, "text indicating male")

        assert outcome.is_valid is False
        assert any("sex" in m.lower() for m in outcome.mismatches)
        assert outcome.mismatch_details[0].model_dump() == {
            "field": "sex",
            "patient_record_value": "female",
            "document_value": "male",
        }

    def test_deterministic_dob_mismatch_overrides_llm_valid_flag(self, service, ai_client_stub):
        ai_client_stub.validate_patient_match.return_value = {
            "is_valid": True,
            "extracted_patient_signals": {
                "full_name": None, "sex": None, "date_of_birth": "1999-01-01", "patient_id": None,
            },
            "mismatches": [],
            "reason": None,
        }

        outcome = service.validate(SAMPLE_PATIENT, "text with a different DOB")

        assert outcome.is_valid is False
        assert any("date of birth" in m.lower() for m in outcome.mismatches)
        assert outcome.mismatch_details[0].model_dump() == {
            "field": "date_of_birth",
            "patient_record_value": "1980-05-14",
            "document_value": "1999-01-01",
        }

    def test_model_and_guardrail_report_each_field_once(self, service, ai_client_stub):
        ai_client_stub.validate_patient_match.return_value = {
            "is_valid": False,
            "extracted_patient_signals": {
                "full_name": "Rawan Yahya",
                "sex": "female",
                "date_of_birth": "2026-07-27",
                "patient_id": "1000",
            },
            "mismatches": [
                "patient_id: document has 1000, record has 1001",
                "date_of_birth: document has 2026-07-27, record has 2004-03-02",
            ],
            "reason": "Patient does not match",
        }
        patient = SAMPLE_PATIENT.model_copy(update={"patient_id": "1001", "date_of_birth": "2004-03-02"})

        outcome = service.validate(patient, "lab report")

        assert len(outcome.mismatches) == 2
        assert sum("patient" in item.lower() and "1000" in item for item in outcome.mismatches) == 1
        assert sum("2026-07-27" in item for item in outcome.mismatches) == 1
        assert [item.model_dump() for item in outcome.mismatch_details] == [
            {
                "field": "date_of_birth",
                "patient_record_value": "2004-03-02",
                "document_value": "2026-07-27",
            },
            {
                "field": "patient_id",
                "patient_record_value": "1001",
                "document_value": "1000",
            },
        ]

    def test_matching_male_patient_with_male_signals_is_valid(self, service, ai_client_stub):
        ai_client_stub.validate_patient_match.return_value = {
            "is_valid": True,
            "extracted_patient_signals": {
                "full_name": "John Smith", "sex": "male", "date_of_birth": "1975-01-01", "patient_id": None,
            },
            "mismatches": [],
            "reason": None,
        }

        outcome = service.validate(SAMPLE_PATIENT_MALE, "text about John Smith")

        assert outcome.is_valid is True

    def test_absence_of_signals_is_not_a_mismatch(self, service, ai_client_stub):
        ai_client_stub.validate_patient_match.return_value = {
            "is_valid": True,
            "extracted_patient_signals": {"full_name": None, "sex": None, "date_of_birth": None, "patient_id": None},
            "mismatches": [],
            "reason": None,
        }

        outcome = service.validate(SAMPLE_PATIENT, "generic text with no identifying info")

        assert outcome.is_valid is True
        assert outcome.mismatches == []
        assert outcome.mismatch_details == []

    def test_structured_llm_mismatch_is_kept_as_a_table_row(self, service, ai_client_stub):
        ai_client_stub.validate_patient_match.return_value = {
            "is_valid": False,
            "extracted_patient_signals": {
                "full_name": "Someone Else", "sex": None, "date_of_birth": None, "patient_id": None,
            },
            "mismatches": [
                {
                    "field": "full_name",
                    "patient_record_value": "Jane Doe",
                    "document_value": "Someone Else",
                }
            ],
            "reason": "Name mismatch",
        }

        outcome = service.validate(SAMPLE_PATIENT, "text about Someone Else")

        assert outcome.mismatch_details[0].model_dump() == {
            "field": "full_name",
            "patient_record_value": "Jane Doe",
            "document_value": "Someone Else",
        }
