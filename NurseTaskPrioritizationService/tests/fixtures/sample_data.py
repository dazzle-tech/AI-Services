"""Sample data for Nurse Task Prioritization Service tests."""
from app.models.schemas import (
    TaskPrioritizationRequest,
    UnitContext,
    NurseContext,
    PatientInput,
    VitalReading,
    LabAlert,
    MedicationTask,
    NursingTask,
    Note,
)

SAMPLE_UNIT_CONTEXT = UnitContext(
    unit_name="Medical Ward A",
    shift="day",
    generated_at="2026-03-16T09:00:00Z"
)

SAMPLE_NURSE_CONTEXT = NurseContext(
    nurse_id="N-204",
    assigned_rooms=["101", "102", "103", "104"]
)

SAMPLE_PATIENT_MINIMAL = PatientInput(
    patient_id="P-1001",
    room="101",
    patient_risk_flags=[],
    vitals=[],
    lab_alerts=[],
    medication_tasks=[],
    nursing_tasks=[],
    notes=[]
)

SAMPLE_PATIENT_FULL = PatientInput(
    patient_id="P-1001",
    room="101",
    patient_risk_flags=["fall_risk"],
    vitals=[
        VitalReading(name="oxygen_saturation", value="88", unit="%", timestamp="2026-03-16T08:55:00Z"),
        VitalReading(name="heart_rate", value="118", unit="bpm", timestamp="2026-03-16T08:55:00Z"),
    ],
    lab_alerts=[
        LabAlert(name="potassium", value="2.9", unit="mmol/L", flag="low", timestamp="2026-03-16T08:40:00Z"),
    ],
    medication_tasks=[
        MedicationTask(
            task_id="MED-1",
            medication_name="Insulin",
            due_time="2026-03-16T09:05:00Z",
            status="pending",
            priority_hint="time_sensitive"
        ),
    ],
    nursing_tasks=[
        NursingTask(
            task_id="TASK-1",
            title="Reassess oxygen therapy",
            due_time="2026-03-16T09:00:00Z",
            status="pending"
        ),
        NursingTask(
            task_id="TASK-2",
            title="Fall prevention rounding",
            due_time="2026-03-16T09:20:00Z",
            status="pending"
        ),
    ],
    notes=[
        Note(type="nurse_note", timestamp="2026-03-16T08:30:00Z", text="Patient short of breath during ambulation."),
    ]
)

SAMPLE_REQUEST_MINIMAL = TaskPrioritizationRequest(
    request_id="req-001",
    unit_context=SAMPLE_UNIT_CONTEXT,
    nurse_context=SAMPLE_NURSE_CONTEXT,
    patients=[SAMPLE_PATIENT_MINIMAL]
)

SAMPLE_REQUEST_FULL = TaskPrioritizationRequest(
    request_id="req-001",
    unit_context=SAMPLE_UNIT_CONTEXT,
    nurse_context=SAMPLE_NURSE_CONTEXT,
    patients=[SAMPLE_PATIENT_FULL]
)

SAMPLE_REQUEST_NO_ID = TaskPrioritizationRequest(
    unit_context=SAMPLE_UNIT_CONTEXT,
    nurse_context=SAMPLE_NURSE_CONTEXT,
    patients=[SAMPLE_PATIENT_FULL]
)
