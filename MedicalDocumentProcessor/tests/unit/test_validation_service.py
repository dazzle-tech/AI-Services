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
