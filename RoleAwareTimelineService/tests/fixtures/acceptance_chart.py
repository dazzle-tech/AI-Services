"""Acceptance chart: 58 years, male, with the documented events and nothing more."""

ACCEPTANCE_PATIENT = {
    "patient_id": "pt-acceptance-58",
    "age": "58 years",
    "gender": "male",
    "diagnoses": [
        {"name": "Type 2 diabetes", "date": "2022-05-01"},
        {"name": "Hypertension", "date": "2021-03-10"},
    ],
    "medications": [
        {"name": "Metformin", "start_date": "2022-05-02", "status": "active"},
        {"name": "Insulin", "start_date": "2023-11-18", "status": "active"},
    ],
    "lab_results": [
        {
            "name": "Troponin",
            "value": "0.8",
            "unit": "ng/mL",
            "date": "2026-03-13",
            "flag": "high",
        }
    ],
    "vitals": [
        {"name": "Blood pressure", "value": "160/100", "date": "2026-03-12"}
    ],
    "procedures": [
        {"name": "Coronary angiography", "date": "2020-02-15", "status": "completed"}
    ],
    "encounters": [
        {"type": "admission", "date": "2026-03-12", "reason": "chest pain"}
    ],
    "notes": [
        {
            "date": "2026-03-12",
            "text": "Admitted with chest pain and shortness of breath.",
        }
    ],
    "allergies": [
        {"name": "Penicillin", "date": "2020-01-01"}
    ],
}

CANONICAL_EVENTS = [
    {
        "date": "2020-01-01",
        "event_type": "allergy",
        "title": "Penicillin allergy",
        "description": "Penicillin allergy recorded on 2020-01-01.",
        "clinical_importance": "high",
        "source": "allergies",
    },
    {
        "date": "2020-02-15",
        "event_type": "procedure",
        "title": "Coronary angiography",
        "description": "Coronary angiography completed on 2020-02-15.",
        "clinical_importance": "medium",
        "source": "procedures",
    },
    {
        "date": "2021-03-10",
        "event_type": "diagnosis",
        "title": "Hypertension",
        "description": "Hypertension diagnosed on 2021-03-10.",
        "clinical_importance": "medium",
        "source": "diagnoses",
    },
    {
        "date": "2022-05-01",
        "event_type": "diagnosis",
        "title": "Type 2 diabetes",
        "description": "Type 2 diabetes diagnosed on 2022-05-01.",
        "clinical_importance": "medium",
        "source": "diagnoses",
    },
    {
        "date": "2022-05-02",
        "event_type": "medication",
        "title": "Metformin",
        "description": "Metformin started on 2022-05-02, status active.",
        "clinical_importance": "medium",
        "source": "medications",
    },
    {
        "date": "2023-11-18",
        "event_type": "medication",
        "title": "Insulin",
        "description": "Insulin started on 2023-11-18, status active.",
        "clinical_importance": "high",
        "source": "medications",
    },
    {
        "date": "2026-03-12",
        "event_type": "admission",
        "title": "Admission for chest pain",
        "description": "Admission for chest pain on 2026-03-12.",
        "clinical_importance": "high",
        "source": "encounters",
    },
    {
        "date": "2026-03-12",
        "event_type": "symptom",
        "title": "Admitted with chest pain and shortness of breath",
        "description": "Admitted with chest pain and shortness of breath.",
        "clinical_importance": "high",
        "source": "notes",
    },
    {
        "date": "2026-03-12",
        "event_type": "vital",
        "title": "Blood pressure 160/100",
        "description": "Blood pressure 160/100 on 2026-03-12.",
        "clinical_importance": "high",
        "source": "vitals",
    },
    {
        "date": "2026-03-13",
        "event_type": "lab",
        "title": "Troponin 0.8 ng/mL",
        "description": "Troponin 0.8 ng/mL, flagged high, on 2026-03-13.",
        "clinical_importance": "high",
        "source": "lab_results",
    },
]

SHARED_SUMMARY = (
    "58-year-old male. Problem list: chest pain and shortness of breath with admission "
    "on 2026-03-12, blood pressure 160/100 on that date, and one troponin of 0.8 ng/mL, "
    "flagged high, on 2026-03-13. Type 2 diabetes diagnosed 2022-05-01, with metformin "
    "active from 2022-05-02 and insulin active from 2023-11-18. Hypertension diagnosed "
    "2021-03-10. Coronary angiography completed 2020-02-15. Penicillin allergy recorded "
    "2020-01-01."
)
