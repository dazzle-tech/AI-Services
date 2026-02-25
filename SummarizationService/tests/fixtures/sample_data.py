"""Sample patient data for testing."""
from app.models.schemas import PatientDataInput, SummaryRequest, SurgeryWithStatus


# Sample patient data fixtures
SAMPLE_PATIENT_MINIMAL = PatientDataInput(
    Age="45 years",
    Gender="Male",
    Diagnosis="Type 2 Diabetes"
)

SAMPLE_PATIENT_COMPLETE = PatientDataInput(
    Age="58 years",
    Gender="Male",
    Diagnosis="Acute ST-Elevation Myocardial Infarction (STEMI)",
    Symptoms=["Chest pain", "Shortness of breath", "Diaphoresis"],
    Medications=["Aspirin 325mg daily", "Metoprolol 50mg BID", "Atorvastatin 40mg daily"],
    Surgeries=[SurgeryWithStatus(name="Appendectomy 2010", status="completed")],
    Allergies=["Penicillin"],
    Medical_Warnings=["Renal impairment"],
    Problems=["Hypertension", "Hyperlipidemia"],
    Vitals={
        "BP": "140/90",
        "HR": "72 bpm",
        "RR": "18",
        "Temp": "98.6 F",
        "SpO2": "98%"
    },
    Lab_Results={
        "Troponin": "0.4 ng/mL",
        "HbA1c": "7.5%",
        "Creatinine": "1.1 mg/dL",
        "LDL": "95 mg/dL"
    }
)

SAMPLE_PATIENT_PEDIATRIC = PatientDataInput(
    Age="5 years",
    Gender="Female",
    Diagnosis="Community-Acquired Pneumonia",
    Symptoms=["Cough", "Fever", "Difficulty breathing"],
    Medications=["Amoxicillin 500mg TID", "Albuterol inhaler PRN"],
    Allergies=["None known"],
    Vitals={
        "BP": "100/60",
        "HR": "110 bpm",
        "RR": "24",
        "Temp": "101.2 F",
        "SpO2": "95%"
    }
)

SAMPLE_PATIENT_ELDERLY = PatientDataInput(
    Age="82 years",
    Gender="Female",
    Diagnosis="Urinary Tract Infection",
    Symptoms=["Dysuria", "Frequency", "Fever"],
    Medications=["Ciprofloxacin 500mg BID", "Acetaminophen 650mg PRN"],
    Allergies=["Sulfa drugs"],
    Problems=["Diabetes", "Hypertension", "Osteoarthritis"],
    Vitals={
        "BP": "150/85",
        "HR": "88 bpm",
        "Temp": "99.8 F"
    }
)

# Sample requests
SAMPLE_REQUEST_MINIMAL = SummaryRequest(
    request_id="test-001",
    patient_data=SAMPLE_PATIENT_MINIMAL
)

SAMPLE_REQUEST_COMPLETE = SummaryRequest(
    request_id="test-002",
    patient_data=SAMPLE_PATIENT_COMPLETE
)

SAMPLE_REQUEST_NO_ID = SummaryRequest(
    patient_data=SAMPLE_PATIENT_COMPLETE
)

