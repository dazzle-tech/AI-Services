"""Sample lab data for testing."""
from app.models.schemas import (
    LabResultItem,
    PatientContext,
    LabInterpretationRequest,
)


SAMPLE_LAB_MINIMAL = [
    LabResultItem(
        name="WBC",
        value="10.5",
        unit="10^9/L",
        reference_range="4.0-11.0",
        flag="normal",
        timestamp="2026-03-16T08:00:00Z",
    ),
]

SAMPLE_LAB_ABNORMAL = [
    LabResultItem(
        name="WBC",
        value="18.2",
        unit="10^9/L",
        reference_range="4.0-11.0",
        flag="high",
        timestamp="2026-03-16T08:00:00Z",
    ),
    LabResultItem(
        name="CRP",
        value="145",
        unit="mg/L",
        reference_range="0-5",
        flag="high",
        timestamp="2026-03-16T08:00:00Z",
    ),
]

SAMPLE_PATIENT_CONTEXT = PatientContext(
    patient_id="P-1001",
    age=58,
    sex="male",
    known_conditions=["Type 2 Diabetes", "Hypertension"],
    medications=["Metformin", "Lisinopril"],
    clinical_context="Admitted with fever and shortness of breath",
)

SAMPLE_HISTORICAL = [
    LabResultItem(
        name="Creatinine",
        value="1.0",
        unit="mg/dL",
        reference_range="0.7-1.3",
        flag="normal",
        timestamp="2026-03-14T08:00:00Z",
    ),
    LabResultItem(
        name="Creatinine",
        value="1.8",
        unit="mg/dL",
        reference_range="0.7-1.3",
        flag="high",
        timestamp="2026-03-16T08:00:00Z",
    ),
]

SAMPLE_REQUEST_MINIMAL = LabInterpretationRequest(
    request_id="req-lab-001",
    lab_results=SAMPLE_LAB_MINIMAL,
)

SAMPLE_REQUEST_FULL = LabInterpretationRequest(
    request_id="req-lab-001",
    patient_context=SAMPLE_PATIENT_CONTEXT,
    lab_results=SAMPLE_LAB_ABNORMAL,
    historical_lab_results=SAMPLE_HISTORICAL,
)

SAMPLE_REQUEST_NO_ID = LabInterpretationRequest(
    patient_context=SAMPLE_PATIENT_CONTEXT,
    lab_results=SAMPLE_LAB_ABNORMAL,
    historical_lab_results=SAMPLE_HISTORICAL,
)
