import pytest
from pydantic import ValidationError

from models.schemas import MedicationValidationRequest


def _base_payload(**overrides):
    payload = {
        "patient": {
            "mrn": "1000",
            "fullName": "John Doe",
            "gender": "Male",
            "dob": "2022-02-02",
        },
        "encounter": {
            "visitId": "160",
            "visitType": "Urgent Visit",
            "plannedStartDate": "2025-12-24",
            "chiefComplaint": "Chest pain",
            "patientAge": "3y 10m 22d",
            "primaryDiagnosis": "I20.0,Unstable angina",
        },
        "listOfDiagnosis": [
            {"type": "Encounter Diagnosis", "value": "I20.0,Unstable angina"}
        ],
        "medications": [
            "Medication Name: Amoxicillin | Active Ingredients: Amoxicillin - 500 mg"
        ],
    }
    payload.update(overrides)
    return payload


def test_allergies_optional_defaults_to_empty():
    request = MedicationValidationRequest(**_base_payload())
    assert request.allergies == []


def test_allergies_accepted_with_cms_shape():
    request = MedicationValidationRequest(
        **_base_payload(
            allergies=[
                {
                    "allergenName": "Penicillin",
                    "allergenType": "MEDICATION",
                    "severity": "SEVERE",
                    "criticality": "High Criticality",
                    "allergicReactions": ["Anaphylaxis", "Urticaria (Hives)"],
                    "status": "ACTIVE",
                }
            ]
        )
    )
    assert len(request.allergies) == 1
    assert request.allergies[0].allergenName == "Penicillin"
    assert request.allergies[0].allergenType == "MEDICATION"
    assert request.allergies[0].status == "ACTIVE"


def test_invalid_allergen_type_rejected():
    with pytest.raises(ValidationError):
        MedicationValidationRequest(
            **_base_payload(
                allergies=[
                    {
                        "allergenName": "Penicillin",
                        "allergenType": "DRUG",
                        "severity": "SEVERE",
                        "criticality": "High Criticality",
                        "allergicReactions": ["Anaphylaxis"],
                        "status": "ACTIVE",
                    }
                ]
            )
        )


def test_invalid_allergic_reaction_rejected():
    with pytest.raises(ValidationError):
        MedicationValidationRequest(
            **_base_payload(
                allergies=[
                    {
                        "allergenName": "Penicillin",
                        "allergenType": "MEDICATION",
                        "severity": "SEVERE",
                        "criticality": "High Criticality",
                        "allergicReactions": ["Unknown Reaction"],
                        "status": "ACTIVE",
                    }
                ]
            )
        )
