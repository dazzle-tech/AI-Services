import pytest
from pydantic import ValidationError

from models.schemas import AllergyDrugValidationRequest


def test_full_payload_parses():
    request = AllergyDrugValidationRequest(
        **{
            "patient": {
                "fullName": "John Doe",
                "gender": "Male",
                "dob": "2022-02-02",
                "chiefComplaint": "Chest pain",
                "primaryDiagnosis": "I20.0,Unstable angina",
            },
            "allergies": [
                {
                    "allergy_description": "Penicillin",
                    "allergy_type_description": "Drug",
                }
            ],
            "drugs": [{"drug_name": "Penicillin"}],
        }
    )
    assert request.patient.fullName == "John Doe"
    assert request.allergies[0].allergy_description == "Penicillin"
    assert request.drugs[0].drug_name == "Penicillin"


def test_patient_is_optional():
    request = AllergyDrugValidationRequest(
        allergies=[{"allergy_description": "Penicillin", "allergy_type_description": "Drug"}],
        drugs=[{"drug_name": "Penicillin"}],
    )
    assert request.patient is None
    assert len(request.drugs) == 1


def test_empty_patient_object_is_allowed():
    request = AllergyDrugValidationRequest(
        patient={},
        allergies=[],
        drugs=[{"drug_name": "Amoxicillin"}],
    )
    assert request.patient is not None
    assert request.patient.fullName is None
    assert request.allergies == []


def test_drugs_required():
    with pytest.raises(ValidationError):
        AllergyDrugValidationRequest(
            allergies=[{"allergy_description": "Penicillin"}],
            drugs=[],
        )


def test_string_allergies_and_drugs_are_coerced():
    request = AllergyDrugValidationRequest(
        allergies=["Penicillin"],
        drugs=["Amoxicillin"],
    )
    assert request.allergies[0].allergy_description == "Penicillin"
    assert request.drugs[0].drug_name == "Amoxicillin"
