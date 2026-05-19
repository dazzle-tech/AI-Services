"""Sample patient record fixtures for testing."""
from app.models.schemas import (
    Alert,
    AlertRequest,
    DiagnosisItem,
    DischargeFollowUpItem,
    ExistingConsultItem,
    ImagingReportItem,
    LabResultItem,
    MedicationItem,
    NoteItem,
    PatientRecordInput,
    VitalItem,
)


SAMPLE_PATIENT_MINIMAL = PatientRecordInput(
    patient_id="P-1001",
    demographics={"age": 58, "sex": "male"},
)

SAMPLE_PATIENT_COMPLETE = PatientRecordInput(
    patient_id="P-1001",
    demographics={"age": 58, "sex": "male"},
    diagnoses=[
        DiagnosisItem(name="Type 2 Diabetes", date="2022-05-01"),
        DiagnosisItem(name="Hypertension", date="2021-03-10"),
    ],
    medications=[
        MedicationItem(name="Lisinopril", start_date="2025-01-01", status="active"),
        MedicationItem(name="Ibuprofen", start_date="2026-03-14", status="active"),
    ],
    lab_results=[
        LabResultItem(
            name="Troponin",
            value="0.8",
            unit="ng/mL",
            reference_range="0.0-0.04",
            flag="high",
            date="2026-03-13",
        ),
        LabResultItem(
            name="Creatinine",
            value="1.8",
            unit="mg/dL",
            reference_range="0.7-1.3",
            flag="high",
            date="2026-03-16",
        ),
        LabResultItem(
            name="WBC",
            value="18.2",
            unit="10^9/L",
            reference_range="4.0-11.0",
            flag="high",
            date="2026-03-16",
        ),
    ],
    historical_lab_results=[
        LabResultItem(
            name="Creatinine",
            value="1.0",
            unit="mg/dL",
            reference_range="0.7-1.3",
            flag="normal",
            date="2026-03-14",
        )
    ],
    vitals=[
        VitalItem(name="blood_pressure", value="92/60", unit="mmHg", date="2026-03-16"),
        VitalItem(name="temperature", value="39.1", unit="C", date="2026-03-16"),
        VitalItem(name="oxygen_saturation", value="89", unit="%", date="2026-03-16"),
    ],
    imaging_reports=[
        ImagingReportItem(
            type="CT Head",
            date="2026-03-15",
            text="Small hyperdense area concerning for possible intracranial hemorrhage.",
        )
    ],
    notes=[
        NoteItem(
            date="2026-03-16",
            author="Nurse A",
            type="nurse_note",
            text="Patient febrile and appears more confused.",
        ),
        NoteItem(
            date="2026-03-16",
            author="Dr. Lee",
            type="progress_note",
            text="Renal function worsened since admission. Monitoring closely.",
        ),
    ],
    existing_consults=[
        ExistingConsultItem(specialty="Cardiology", date="2026-03-12", status="completed")
    ],
    problem_list=["Acute kidney injury", "Chest pain", "Shortness of breath"],
    discharge_follow_up=[DischargeFollowUpItem(specialty="Nephrology", scheduled=False)],
)

SAMPLE_REQUEST_MINIMAL = AlertRequest(request_id="test-001", patient_record=SAMPLE_PATIENT_MINIMAL)
SAMPLE_REQUEST_COMPLETE = AlertRequest(request_id="test-002", patient_record=SAMPLE_PATIENT_COMPLETE)
SAMPLE_REQUEST_NO_ID = AlertRequest(patient_record=SAMPLE_PATIENT_COMPLETE)

SAMPLE_ALERT = Alert(
    alert_id="ALT-001",
    category="urgent_escalation",
    severity="critical",
    title="Possible severe clinical deterioration needs urgent review",
    reason=(
        "Fever, hypotension, hypoxia, confusion, and inflammatory markers may indicate "
        "serious deterioration requiring immediate assessment."
    ),
    recommended_specialty="Infectious Disease",
    supporting_evidence=[
        "Vital temperature 39.1 C on 2026-03-16",
        "Vital oxygen_saturation 89 % on 2026-03-16",
    ],
    suggested_action=(
        "Urgently review patient status and determine whether escalation and specialist input are required."
    ),
    confidence="high",
)

UNGROUNDED_ALERT = Alert(
    alert_id="ALT-999",
    category="specialist_consult",
    severity="medium",
    title="Consider dermatology consultation",
    reason="Possible rash may require specialty review.",
    recommended_specialty="Dermatology",
    supporting_evidence=["Diffuse rash documented on exam on 2026-03-15"],
    suggested_action="Review for possible dermatology involvement.",
    confidence="medium",
)
