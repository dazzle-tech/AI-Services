from app.core.constants import SupportedLanguage
from app.models.schemas import AutoPopulationRequest
from app.services.auto_population_service import AutoPopulationService
from app.services.validation import (
    build_structured_fields,
    check_contradictions,
    normalize_history_of_present_illness,
)


def make_request() -> AutoPopulationRequest:
    return AutoPopulationRequest(
        request_id="req_postman_001",
        input_language=SupportedLanguage.EN,
        output_language=SupportedLanguage.EN,
        user_text=(
            "Patient is a 65-year-old male presenting with acute chest pain that started 2 hours ago. "
            "Blood pressure is 150/90, heart rate 95 bpm. Patient has history of hypertension and is "
            "currently taking Lisinopril 10mg daily. No known allergies. Assessment: Possible acute "
            "coronary syndrome. Plan: EKG, cardiac enzymes, aspirin 325mg."
        ),
        patient_data={
            "medications": [
                {
                    "name": "Lisinopril",
                    "dosage": "10mg",
                    "frequency": "daily",
                }
            ],
            "allergies": [],
            "vitals": {
                "bp": "140/85",
                "hr": "92",
            },
            "past_medical_history": ["hypertension"],
        },
        expected_output=[
            "chief_complaint",
            "history_of_present_illness",
            "diagnosis",
            "medications",
            "vitals",
            "assessment",
            "plan",
        ],
    )


def test_plan_extracted_as_list_is_coerced_to_string():
    structured_fields, warnings = build_structured_fields(
        {
            "chief_complaint": "Acute chest pain",
            "plan": ["EKG", "cardiac enzymes", "aspirin 325mg"],
        }
    )

    assert structured_fields.plan == "EKG, cardiac enzymes, aspirin 325mg"
    assert structured_fields.chief_complaint == "Acute chest pain"
    assert any("converted to comma-separated string" in warning.message for warning in warnings)


def test_plan_extracted_as_string_remains_string():
    structured_fields, warnings = build_structured_fields(
        {
            "plan": "EKG, cardiac enzymes, aspirin 325mg",
        }
    )

    assert structured_fields.plan == "EKG, cardiac enzymes, aspirin 325mg"
    assert warnings == []


def test_diagnosis_and_procedures_strings_are_wrapped_as_lists():
    structured_fields, warnings = build_structured_fields(
        {
            "diagnosis": "Possible acute coronary syndrome",
            "procedures": "EKG completed",
        }
    )

    assert structured_fields.diagnosis == ["Possible acute coronary syndrome"]
    assert structured_fields.procedures == ["EKG completed"]
    assert len(warnings) == 2


def test_medications_list_is_preserved():
    structured_fields, warnings = build_structured_fields(
        {
            "medications": [
                {
                    "name": "Lisinopril",
                    "dosage": "10mg",
                    "frequency": "daily",
                }
            ]
        }
    )

    assert structured_fields.medications == [
        {
            "name": "Lisinopril",
            "dosage": "10mg",
            "frequency": "daily",
        }
    ]
    assert warnings == []


def test_medications_plain_string_list_is_coerced_to_objects():
    structured_fields, warnings = build_structured_fields(
        {
            "medications": ["Lisinopril 10mg daily", "Aspirin 325mg"],
        }
    )

    assert structured_fields.medications == [
        {"name": "Lisinopril 10mg daily"},
        {"name": "Aspirin 325mg"},
    ]
    assert warnings == []


def test_allergies_empty_list_stays_empty():
    structured_fields, warnings = build_structured_fields({"allergies": []})

    assert structured_fields.allergies == []
    assert warnings == []


def test_vitals_string_is_parsed_into_dict():
    structured_fields, warnings = build_structured_fields(
        {
            "vitals": "BP 150/90, HR 95 bpm",
        }
    )

    assert structured_fields.vitals["bp"] == "150/90"
    assert structured_fields.vitals["hr"] == "95 bpm"
    assert structured_fields.vitals["raw"] == "BP 150/90, HR 95 bpm"
    assert len(warnings) == 1


def test_hpi_retains_age_and_gender():
    hpi = normalize_history_of_present_illness(
        "Patient is a 65-year-old male presenting with acute chest pain that started 2 hours ago.",
        "Acute chest pain that started 2 hours ago"
    )

    assert hpi == "Patient is a 65-year-old male presenting with acute chest pain that started 2 hours ago."


def test_successful_extraction_populates_expected_fields():
    structured_fields, warnings = build_structured_fields(
        {
            "chief_complaint": "Acute chest pain",
            "history_of_present_illness": "65-year-old male presenting with acute chest pain that started 2 hours ago.",
            "diagnosis": ["Possible acute coronary syndrome"],
            "medications": [
                {
                    "name": "Lisinopril",
                    "dosage": "10mg",
                    "frequency": "daily",
                }
            ],
            "allergies": [],
            "assessment": "Possible acute coronary syndrome",
            "plan": ["EKG", "cardiac enzymes", "aspirin 325mg"],
            "past_medical_history": "Hypertension",
        }
    )

    assert structured_fields.chief_complaint == "Acute chest pain"
    assert structured_fields.history_of_present_illness.startswith("65-year-old male")
    assert structured_fields.diagnosis == ["Possible acute coronary syndrome"]
    assert structured_fields.medications[0]["name"] == "Lisinopril"
    assert structured_fields.allergies == []
    assert structured_fields.assessment == "Possible acute coronary syndrome"
    assert structured_fields.plan == "EKG, cardiac enzymes, aspirin 325mg"
    assert structured_fields.past_medical_history == "Hypertension"
    assert warnings, "Expected a conversion warning for the list-based plan field"


def test_partial_validation_failure_does_not_clear_other_fields():
    structured_fields, warnings = build_structured_fields(
        {
            "chief_complaint": "Acute chest pain",
            "plan": ["EKG", "cardiac enzymes", "aspirin 325mg"],
            "medications": 123,
            "vitals": "BP 150/90, HR 95 bpm",
        }
    )

    assert structured_fields.chief_complaint == "Acute chest pain"
    assert structured_fields.plan == "EKG, cardiac enzymes, aspirin 325mg"
    assert structured_fields.medications is None
    assert structured_fields.vitals["bp"] == "150/90"
    assert any(warning.field_name == "medications" for warning in warnings)


def test_multiple_malformed_fields_still_preserve_valid_fields():
    structured_fields, warnings = build_structured_fields(
        {
            "chief_complaint": "Acute chest pain",
            "plan": ["EKG", "cardiac enzymes", "aspirin 325mg"],
            "diagnosis": "Possible acute coronary syndrome",
            "procedures": "EKG completed",
            "vitals": "BP 150/90, HR 95 bpm",
            "medications": ["Lisinopril 10mg daily", "Aspirin 325mg"],
            "allergies": [],
            "assessment": "Possible acute coronary syndrome",
        }
    )

    assert structured_fields.chief_complaint == "Acute chest pain"
    assert structured_fields.plan == "EKG, cardiac enzymes, aspirin 325mg"
    assert structured_fields.diagnosis == ["Possible acute coronary syndrome"]
    assert structured_fields.procedures == ["EKG completed"]
    assert structured_fields.vitals["bp"] == "150/90"
    assert structured_fields.medications[0]["name"] == "Lisinopril 10mg daily"
    assert structured_fields.allergies == []
    assert structured_fields.assessment == "Possible acute coronary syndrome"
    assert len(warnings) >= 3


def test_conflicting_vitals_flags_bp_and_hr():
    contradictions = check_contradictions(
        {
            "vitals": {
                "bp": "150/90",
                "hr": "95 bpm",
            }
        },
        {
            "vitals": {
                "bp": "140/85",
                "hr": "92",
            }
        },
    )

    field_names = {contradiction.field_name for contradiction in contradictions}

    assert "vitals.bp" in field_names
    assert "vitals.hr" in field_names


def test_every_contradiction_generates_matching_uncertainty_flag(monkeypatch):
    class DummyAIClient:
        def __init__(self):
            self.model = "qwen3:1.7b"

        def extract_structured_data(self, **kwargs):
            return {
                "structured_fields": {
                    "chief_complaint": "Acute chest pain",
                    "history_of_present_illness": "65-year-old male presenting with acute chest pain that started 2 hours ago.",
                    "medications": [
                        {
                            "name": "Lisinopril",
                            "dosage": "10mg",
                            "frequency": "daily",
                        }
                    ],
                    "vitals": {
                        "bp": "150/90",
                        "hr": "95 bpm",
                    },
                    "assessment": "Possible acute coronary syndrome",
                    "plan": "EKG, cardiac enzymes, aspirin 325mg",
                    "allergies": [],
                },
                "uncertainty_flags": [],
                "contradictions": [],
                "source_trace": [],
            }

    monkeypatch.setattr("app.services.auto_population_service.AIClient", DummyAIClient)

    service = AutoPopulationService()
    response = service.process_request(make_request())
    field_names = {flag.field_name for flag in response.uncertainty_flags}

    assert "vitals.bp" in field_names
    assert "vitals.hr" in field_names


def test_medication_source_trace_prefers_user_text(monkeypatch):
    class DummyAIClient:
        def __init__(self):
            self.model = "qwen3:1.7b"

        def extract_structured_data(self, **kwargs):
            return {
                "structured_fields": {
                    "medications": [
                        {
                            "name": "Lisinopril",
                            "dosage": "10mg",
                            "frequency": "daily",
                        }
                    ],
                    "allergies": [],
                    "vitals": {
                        "bp": "140/85",
                        "hr": "92",
                    },
                    "plan": "EKG",
                },
                "uncertainty_flags": [],
                "contradictions": [],
                "source_trace": [
                    {
                        "field_name": "medications",
                        "source": "patient_record",
                        "extraction_method": "direct",
                    }
                ],
            }

    monkeypatch.setattr("app.services.auto_population_service.AIClient", DummyAIClient)

    service = AutoPopulationService()
    response = service.process_request(make_request())

    med_sources = [trace.source for trace in response.source_trace if trace.field_name == "medications"]
    assert "user_text" in med_sources


def test_planned_procedures_are_not_extracted_as_completed(monkeypatch):
    class DummyAIClient:
        def __init__(self):
            self.model = "qwen3:1.7b"

        def extract_structured_data(self, **kwargs):
            return {
                "structured_fields": {
                    "procedures": ["EKG", "cardiac enzymes"],
                    "plan": "EKG, cardiac enzymes, aspirin 325mg",
                    "allergies": [],
                },
                "uncertainty_flags": [],
                "contradictions": [],
                "source_trace": [],
            }

    monkeypatch.setattr("app.services.auto_population_service.AIClient", DummyAIClient)

    service = AutoPopulationService()
    response = service.process_request(make_request())

    assert response.structured_fields.procedures is None


def test_no_known_allergies_normalize_consistently(monkeypatch):
    class DummyAIClient:
        def __init__(self):
            self.model = "qwen3:1.7b"

        def extract_structured_data(self, **kwargs):
            return {
                "structured_fields": {
                    "allergies": ["No known allergies"],
                    "vitals": {
                        "bp": "140/85",
                        "hr": "92",
                    },
                },
                "uncertainty_flags": [],
                "contradictions": [],
                "source_trace": [],
            }

    monkeypatch.setattr("app.services.auto_population_service.AIClient", DummyAIClient)

    service = AutoPopulationService()
    response = service.process_request(make_request())

    assert response.structured_fields.allergies == []


def test_service_pipeline_preserves_valid_fields_when_plan_is_a_list(monkeypatch):
    class DummyAIClient:
        def __init__(self):
            self.model = "qwen3:1.7b"

        def extract_structured_data(self, **kwargs):
            return {
                "structured_fields": {
                    "chief_complaint": "Acute chest pain",
                    "history_of_present_illness": "65-year-old male presenting with acute chest pain that started 2 hours ago.",
                    "diagnosis": ["Possible acute coronary syndrome"],
                    "medications": [
                        {
                            "name": "Lisinopril",
                            "dosage": "10mg",
                            "frequency": "daily",
                        }
                    ],
                    "allergies": [],
                    "assessment": "Possible acute coronary syndrome",
                    "plan": ["EKG", "cardiac enzymes", "aspirin 325mg"],
                    "vitals": {
                        "bp": "150/90",
                        "hr": "95 bpm",
                    },
                },
                "uncertainty_flags": [],
                "contradictions": [],
                "source_trace": [
                    {
                        "field_name": "chief_complaint",
                        "source": "user_text",
                        "extraction_method": "direct",
                    }
                ],
            }

    monkeypatch.setattr("app.services.auto_population_service.AIClient", DummyAIClient)

    service = AutoPopulationService()
    response = service.process_request(make_request())

    assert response.structured_fields.chief_complaint == "Acute chest pain"
    assert response.structured_fields.plan == "EKG, cardiac enzymes, aspirin 325mg"
    assert response.structured_fields.medications[0]["name"] == "Lisinopril"
    assert response.structured_fields.vitals["bp"] == "150/90"
    assert response.structured_fields.vitals["hr"] == "95 bpm"

    serialized = response.model_dump()
    assert serialized["structured_fields"]["plan"] == "EKG, cardiac enzymes, aspirin 325mg"
    assert serialized["structured_fields"]["chief_complaint"] == "Acute chest pain"
