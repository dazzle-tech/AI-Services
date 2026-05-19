"""Sample discharge planning data for testing."""
from app.models.schemas import (
    DischargePlanningRequest,
    PatientContext,
    ClinicalData,
    OperationalData,
    VitalReading,
    PendingTest,
    ClinicalNote,
    FollowUpAppointment,
    PatientEducation,
    EquipmentNeed,
)


SAMPLE_PATIENT_CONTEXT_MINIMAL = PatientContext(
    patient_id="P-1001",
    primary_diagnosis="Pneumonia",
)

SAMPLE_PATIENT_CONTEXT_FULL = PatientContext(
    patient_id="P-1001",
    admission_date="2026-03-10",
    primary_diagnosis="Pneumonia",
    secondary_diagnoses=["Type 2 Diabetes", "Hypertension"],
    current_status="improving",
)

SAMPLE_CLINICAL_MINIMAL = ClinicalData()

SAMPLE_CLINICAL_FULL = ClinicalData(
    latest_vitals=[
        VitalReading(name="temperature", value="37.1", unit="C", timestamp="2026-03-16T08:00:00Z"),
        VitalReading(name="oxygen_saturation", value="95", unit="%", timestamp="2026-03-16T08:00:00Z"),
    ],
    pending_tests=[PendingTest(name="blood culture", status="pending")],
    active_problems=["Needs home oxygen assessment"],
    medications_current=["Amoxicillin", "Metformin"],
    medications_planned_for_discharge=["Amoxicillin", "Metformin", "Prednisone"],
    notes=[
        ClinicalNote(
            type="progress_note",
            timestamp="2026-03-16T07:30:00Z",
            text="Patient clinically improved. May be ready for discharge if home oxygen not required.",
        )
    ],
)

SAMPLE_OPERATIONAL_MINIMAL = OperationalData()

SAMPLE_OPERATIONAL_FULL = OperationalData(
    follow_up_appointments=[FollowUpAppointment(service="Pulmonology", scheduled=False)],
    patient_education=[
        PatientEducation(topic="antibiotic adherence", completed=True),
        PatientEducation(topic="warning signs and return precautions", completed=False),
    ],
    transport_status="available",
    home_support="family_available",
    equipment_needs=[EquipmentNeed(name="home oxygen", confirmed=False)],
)

SAMPLE_REQUEST_MINIMAL = DischargePlanningRequest(
    request_id="req-discharge-001",
    patient_context=SAMPLE_PATIENT_CONTEXT_MINIMAL,
    clinical_data=SAMPLE_CLINICAL_MINIMAL,
    operational_data=SAMPLE_OPERATIONAL_MINIMAL,
)

SAMPLE_REQUEST_FULL = DischargePlanningRequest(
    request_id="req-discharge-001",
    patient_context=SAMPLE_PATIENT_CONTEXT_FULL,
    clinical_data=SAMPLE_CLINICAL_FULL,
    operational_data=SAMPLE_OPERATIONAL_FULL,
)

SAMPLE_REQUEST_NO_ID = DischargePlanningRequest(
    patient_context=SAMPLE_PATIENT_CONTEXT_FULL,
    clinical_data=SAMPLE_CLINICAL_FULL,
    operational_data=SAMPLE_OPERATIONAL_FULL,
)
