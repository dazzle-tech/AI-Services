"""Schema constraints for the chart extract and the response."""
import pytest
from pydantic import ValidationError

from app.models.schemas import (
    LabResultEntry,
    MedicationEntry,
    PatientDataInput,
    RoleTimelineRequest,
    TimelineEvent,
    VitalEntry,
)


def test_medication_and_vital_schemas_do_not_accept_dose_or_unit_fields():
    """Dose, route, frequency, and vital units are not part of the contract."""
    assert "dose" not in MedicationEntry.model_fields
    assert "route" not in MedicationEntry.model_fields
    assert "frequency" not in MedicationEntry.model_fields
    assert "unit" not in VitalEntry.model_fields
    assert "unit" in LabResultEntry.model_fields


def test_extra_dose_and_vital_unit_are_dropped():
    """Stray dose and vital-unit fields never enter the chart passed to the model."""
    patient = PatientDataInput.model_validate(
        {
            "patient_id": "pt-1",
            "medications": [
                {
                    "name": "Insulin",
                    "start_date": "2023-11-18",
                    "status": "active",
                    "dose": "10 units",
                    "route": "subcutaneous",
                    "frequency": "twice daily",
                }
            ],
            "vitals": [
                {"name": "Blood pressure", "value": "160/100", "date": "2026-03-12", "unit": "mmHg"}
            ],
        }
    )
    dumped = patient.model_dump()
    assert "dose" not in dumped["medications"][0]
    assert dumped["medications"][0]["name"] == "Insulin"
    assert "unit" not in dumped["vitals"][0]
    assert dumped["vitals"][0]["value"] == "160/100"


def test_viewer_role_is_required_and_limited():
    """Only nurse, radiologist, and cardiologist are accepted."""
    RoleTimelineRequest.model_validate(
        {"viewer_role": "Nurse", "patient_data": {"patient_id": "pt-1"}}
    )
    with pytest.raises(ValidationError):
        RoleTimelineRequest.model_validate({"patient_data": {"patient_id": "pt-1"}})
    with pytest.raises(ValidationError):
        RoleTimelineRequest.model_validate(
            {"viewer_role": "pharmacist", "patient_data": {"patient_id": "pt-1"}}
        )


def test_patient_id_is_required():
    """A chart extract needs a patient id."""
    with pytest.raises(ValidationError):
        PatientDataInput.model_validate({"age": "58 years"})


def test_timeline_event_requires_an_id_and_known_type():
    """Response events use the closed event-type list."""
    event = TimelineEvent(
        event_id="evt-001",
        date="2026-03-13",
        event_type="labs",
        title="Troponin",
        description="Troponin 0.8 ng/mL, flagged high.",
        clinical_importance="high",
        source="lab",
    )
    assert event.event_type == "lab"
    assert event.source == "lab_results"
    with pytest.raises(ValidationError):
        TimelineEvent(
            event_id="",
            date="2026-03-13",
            event_type="lab",
            title="Troponin",
            description="Troponin 0.8 ng/mL.",
            clinical_importance="high",
            source="lab_results",
        )
