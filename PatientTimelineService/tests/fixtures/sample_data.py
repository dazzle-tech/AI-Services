"""Sample patient data for testing."""
from app.models.schemas import (
    AllergyEntry,
    DiagnosisEntry,
    EncounterEntry,
    LabResultEntry,
    MedicationEntry,
    NoteEntry,
    PatientContext,
    ProcedureEntry,
    TimelineEvent,
    TimelineRequest,
    VitalEntry,
)


SAMPLE_REQUEST_MINIMAL = TimelineRequest(
    request_id="test-001",
    patient_context=PatientContext(age="58 years", sex="Male"),
    diagnoses=[
        DiagnosisEntry(name="Hypertension", date="2021-03-10")
    ]
)

SAMPLE_REQUEST_COMPLETE = TimelineRequest(
    request_id="test-002",
    patient_context=PatientContext(age="58 years", sex="Male"),
    diagnoses=[
        DiagnosisEntry(name="Type 2 Diabetes", date="2022-05-01"),
        DiagnosisEntry(name="Hypertension", date="2021-03-10")
    ],
    medications=[
        MedicationEntry(name="Metformin", start_date="2022-05-02", end_date=None, status="active"),
        MedicationEntry(name="Insulin", start_date="2023-11-18", end_date=None, status="active")
    ],
    lab_results=[
        LabResultEntry(name="Troponin", value="0.8", unit="ng/mL", timestamp="2026-03-13", flag="high")
    ],
    vitals=[
        VitalEntry(name="BP", value="160/100", date="2026-03-12")
    ],
    procedures=[
        ProcedureEntry(name="Coronary angiography", date="2020-02-15", status="completed")
    ],
    encounters=[
        EncounterEntry(type="admission", date="2026-03-12", reason="Chest pain")
    ],
    notes=[
        NoteEntry(
            date="2026-03-12",
            author="Dr. Smith",
            type="admission_note",
            text="Patient admitted with chest pain and shortness of breath."
        )
    ],
    allergies=[
        AllergyEntry(name="Penicillin", date="2020-01-01")
    ]
)

SAMPLE_REQUEST_NO_ID = TimelineRequest(
    patient_context=SAMPLE_REQUEST_COMPLETE.patient_context,
    diagnoses=SAMPLE_REQUEST_COMPLETE.diagnoses,
    medications=SAMPLE_REQUEST_COMPLETE.medications,
    lab_results=SAMPLE_REQUEST_COMPLETE.lab_results,
    vitals=SAMPLE_REQUEST_COMPLETE.vitals,
    procedures=SAMPLE_REQUEST_COMPLETE.procedures,
    encounters=SAMPLE_REQUEST_COMPLETE.encounters,
    notes=SAMPLE_REQUEST_COMPLETE.notes,
    allergies=SAMPLE_REQUEST_COMPLETE.allergies,
)

SAMPLE_TIMELINE_EVENTS = [
    TimelineEvent(
        date="2020-02-15",
        event_type="procedure",
        title="Coronary angiography performed",
        description="Completed coronary angiography procedure.",
        clinical_importance="high",
        source="procedures"
    ),
    TimelineEvent(
        date="2026-03-12",
        event_type="admission",
        title="Admitted with chest pain",
        description="Hospital admission due to chest pain.",
        clinical_importance="high",
        source="encounters"
    )
]
