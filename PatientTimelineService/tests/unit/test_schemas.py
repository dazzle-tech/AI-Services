"""Unit tests for Pydantic schemas."""
import os

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    Demographics,
    DiagnosisEntry,
    PatientDataInput,
    ProcessingMetadata,
    TimelineEvent,
    TimelineRequest,
    TimelineResponse,
)

TEST_MODEL = os.getenv("OPENAI_MODEL", "")


class TestPatientDataInput:
    """Test PatientDataInput schema validation."""

    def test_valid_minimal_data(self):
        """Test valid minimal patient data."""
        data = PatientDataInput(
            patient_id="12345",
            demographics=Demographics(age="58 years", gender="Male"),
            diagnoses=[DiagnosisEntry(name="Hypertension", date="2021-03-10")]
        )
        assert data.patient_id == "12345"
        assert data.demographics.age == "58 years"
        assert data.diagnoses[0].name == "Hypertension"
        assert data.medications == []

    def test_valid_complete_defaults(self):
        """Test that optional collections default to empty lists."""
        data = PatientDataInput(
            patient_id="12345"
        )
        assert data.diagnoses == []
        assert data.medications == []
        assert data.lab_results == []
        assert data.vitals == []
        assert data.procedures == []
        assert data.encounters == []
        assert data.notes == []
        assert data.allergies == []

    def test_patient_id_required(self):
        """Test that patient_id is required."""
        with pytest.raises(ValidationError):
            PatientDataInput()

    def test_patient_id_cannot_be_empty(self):
        """Test that patient_id cannot be empty."""
        with pytest.raises(ValidationError, match="patient_id cannot be empty"):
            PatientDataInput(patient_id="")

    def test_diagnosis_requires_name(self):
        """Test that diagnosis name is required."""
        with pytest.raises(ValidationError):
            PatientDataInput(
                patient_id="12345",
                diagnoses=[{"date": "2021-03-10"}]
            )


class TestTimelineRequest:
    """Test TimelineRequest schema."""

    def test_valid_request_with_id(self):
        """Test valid request with request_id."""
        request = TimelineRequest(
            request_id="test-123",
            patient_data=PatientDataInput(patient_id="12345")
        )
        assert request.request_id == "test-123"
        assert request.patient_data.patient_id == "12345"

    def test_valid_request_without_id(self):
        """Test valid request without request_id."""
        request = TimelineRequest(
            patient_data=PatientDataInput(patient_id="12345")
        )
        assert request.request_id is None
        assert request.patient_data is not None

    def test_patient_data_required(self):
        """Test that patient_data is required."""
        with pytest.raises(ValidationError):
            TimelineRequest(request_id="test-123")


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
        """Test that invalid event types are rejected."""
        with pytest.raises(ValidationError):
            TimelineEvent(
                date="2021-03-10",
                event_type="note",
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
