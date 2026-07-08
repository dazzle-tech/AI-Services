"""Unit tests for Pydantic schemas."""
import os

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    DiagnosisEntry,
    LabResultEntry,
    MedicationEntry,
    PatientContext,
    ProcessingMetadata,
    TimelineEvent,
    TimelineRequest,
    TimelineResponse,
)

TEST_MODEL = os.getenv("OPENAI_MODEL", "")


class TestPatientContext:
    """Test PatientContext schema validation."""

    def test_valid_patient_context(self):
        """Test valid patient context data."""
        context = PatientContext(age="58 years", sex="Male")
        assert context.age == "58 years"
        assert context.sex == "Male"
        assert context.known_conditions == []

    def test_gender_alias_accepted(self):
        """Test that 'gender' is accepted as an alias for 'sex'."""
        context = PatientContext.model_validate({"age": "10 Years", "gender": "FEMALE"})
        assert context.sex == "FEMALE"

    def test_known_conditions_defaults_empty(self):
        """Test that known_conditions defaults to an empty list."""
        context = PatientContext()
        assert context.known_conditions == []


class TestTimelineRequest:
    """Test TimelineRequest schema (canonical flat shape)."""

    def test_valid_flat_request(self):
        """Test a valid flat request with patient_context and lab_results."""
        request = TimelineRequest.model_validate({
            "request_id": "req-1",
            "patient_context": {"age": "10 Years", "sex": "FEMALE", "known_conditions": []},
            "lab_results": [
                {
                    "name": "CBC1",
                    "value": "25.00",
                    "unit": "Ratio",
                    "reference_range": "5.0 - 10.0",
                    "flag": "critical_upper",
                    "timestamp": "2026-04-20T13:31:06.908451Z",
                }
            ],
            "medications": [
                {"name": "nexium", "start_date": "2026-07-07T21:00:00.000Z", "end_date": None}
            ],
        })

        assert request.request_id == "req-1"
        assert request.patient_context.age == "10 Years"
        assert request.patient_context.sex == "FEMALE"
        assert request.lab_results[0].timestamp == "2026-04-20T13:31:06.908451Z"
        assert request.medications[0].name == "nexium"

    def test_flat_request_dump_matches_input_shape(self):
        """Test that the dumped request preserves the canonical field names."""
        payload = {
            "request_id": "req-2",
            "patient_context": {"age": "10 Years", "sex": "FEMALE", "known_conditions": []},
            "lab_results": [
                {
                    "name": "CBC1",
                    "value": "25.00",
                    "unit": "Ratio",
                    "reference_range": "5.0 - 10.0",
                    "flag": "critical_upper",
                    "timestamp": "2026-04-20T13:31:06.908451Z",
                }
            ],
            "medications": [
                {"name": "nexium", "start_date": "2026-07-07T21:00:00.000Z", "end_date": None}
            ],
        }
        request = TimelineRequest.model_validate(payload)
        dumped = request.model_dump()

        assert dumped["patient_context"] == payload["patient_context"]
        assert dumped["lab_results"] == payload["lab_results"]
        assert dumped["medications"] == payload["medications"]

    def test_valid_request_without_id(self):
        """Test valid request without request_id."""
        request = TimelineRequest(patient_context=PatientContext(age="58 years", sex="Male"))
        assert request.request_id is None
        assert request.patient_context is not None

    def test_defaults_to_empty_lists(self):
        """Test that optional collections default to empty lists."""
        request = TimelineRequest()
        assert request.diagnoses == []
        assert request.medications == []
        assert request.lab_results == []
        assert request.vitals == []
        assert request.procedures == []
        assert request.encounters == []
        assert request.notes == []
        assert request.allergies == []

    def test_legacy_nested_shape_still_accepted(self):
        """Test that the old {"patient_data": {...}} shape still validates."""
        request = TimelineRequest.model_validate({
            "request_id": "test-123",
            "patient_data": {
                "patient_id": "12345",
                "demographics": {"age": "58 years", "gender": "Male"},
                "diagnoses": [{"name": "Hypertension", "date": "2021-03-10"}],
            },
        })
        assert request.request_id == "test-123"
        assert request.patient_context.age == "58 years"
        assert request.patient_context.sex == "Male"
        assert request.diagnoses[0].name == "Hypertension"

    def test_diagnosis_requires_name(self):
        """Test that diagnosis name is required."""
        with pytest.raises(ValidationError):
            TimelineRequest(diagnoses=[{"date": "2021-03-10"}])


class TestLabResultEntry:
    """Test LabResultEntry schema."""

    def test_timestamp_field(self):
        """Test that 'timestamp' populates the lab result date."""
        entry = LabResultEntry.model_validate({
            "name": "CBC1",
            "value": "25.00",
            "unit": "Ratio",
            "reference_range": "5.0 - 10.0",
            "flag": "critical_upper",
            "timestamp": "2026-04-20T13:31:06.908451Z",
        })
        assert entry.timestamp == "2026-04-20T13:31:06.908451Z"

    def test_date_alias_accepted(self):
        """Test that legacy 'date' key still populates timestamp."""
        entry = LabResultEntry.model_validate({
            "name": "Troponin",
            "value": "0.8",
            "date": "2026-03-13",
        })
        assert entry.timestamp == "2026-03-13"


class TestMedicationEntry:
    """Test MedicationEntry schema."""

    def test_status_omitted_when_not_provided(self):
        """Test that status is excluded from output when not supplied."""
        entry = MedicationEntry(name="nexium", start_date="2026-07-07T21:00:00.000Z", end_date=None)
        dumped = entry.model_dump()
        assert "status" not in dumped
        assert dumped["end_date"] is None

    def test_status_included_when_provided(self):
        """Test that status is included in output when supplied."""
        entry = MedicationEntry(name="Metformin", start_date="2022-05-02", status="active")
        dumped = entry.model_dump()
        assert dumped["status"] == "active"


class TestTimelineResponse:
    """Test TimelineResponse schema."""

    def test_valid_response(self):
        """Test valid response."""
        response = TimelineResponse(
            request_id="test-123",
            timeline=[
                TimelineEvent(
                    date="2021-03-10",
                    event_type="diagnosis",
                    title="Hypertension diagnosed",
                    description="Hypertension documented.",
                    clinical_importance="medium",
                    source="diagnoses"
                )
            ],
            summary="Chronological timeline generated successfully.",
            processing_metadata=ProcessingMetadata(
                model=TEST_MODEL,
                timestamp="2026-03-23T09:00:00",
                input_fields_count=3,
                timeline_event_count=1
            )
        )
        assert response.request_id == "test-123"
        assert response.timeline[0].event_type == "diagnosis"
        assert response.processing_metadata.model == TEST_MODEL

    def test_invalid_event_type_rejected(self):
        """Test that unsupported event types are rejected."""
        with pytest.raises(ValidationError):
            TimelineEvent(
                date="2021-03-10",
                event_type="not_a_real_event_type",
                title="Clinical note",
                description="Example note event.",
                clinical_importance="low",
                source="notes"
            )

    def test_event_type_aliases_are_normalized(self):
        """Test that common model aliases are normalized to supported event types."""
        vital_event = TimelineEvent(
            date="2026-03-12",
            event_type="vitals",
            title="Blood pressure elevated",
            description="BP recorded at 160/100.",
            clinical_importance="medium",
            source="vitals"
        )
        encounter_event = TimelineEvent(
            date="2026-03-12",
            event_type="encounters",
            title="Admitted with chest pain",
            description="Hospital admission due to chest pain.",
            clinical_importance="high",
            source="encounters"
        )

        assert vital_event.event_type == "vital"
        assert encounter_event.event_type == "admission"

    def test_summary_required(self):
        """Test that summary is required."""
        with pytest.raises(ValidationError):
            TimelineResponse(
                request_id="test-123",
                timeline=[],
                processing_metadata=ProcessingMetadata(
                    model=TEST_MODEL,
                    timestamp="2026-03-23T09:00:00",
                    input_fields_count=1,
                    timeline_event_count=0
                )
            )
