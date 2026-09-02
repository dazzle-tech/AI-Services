"""
conftest.py
-----------
Shared pytest fixtures available to all test files.
"""

import pytest
from app.models.schemas import Patient, Vitals, Medication, NurseNote


@pytest.fixture
def critical_patient() -> Patient:
    """A patient that should be classified as CRITICAL by the prompt logic."""
    return Patient(
        patient_id="pt_001",
        name="Margaret O'Brien",
        age=72,
        bed="4A",
        diagnosis="Community-acquired pneumonia",
        admission_date="2025-03-09",
        vitals=Vitals(hr=108, bp="94/61", temp=38.6, rr=22, spo2=91, last_updated="14:45"),
        medications=[
            Medication(name="Amoxicillin-Clavulanate 1.2g IV", route="IV", due="15:00", status="pending"),
            Medication(name="Paracetamol 1g", route="Oral", due="12:00", status="given"),
        ],
        pending_orders=[
            "Repeat chest X-ray ordered — awaiting porter",
            "Blood cultures x2 — not yet collected",
        ],
        alerts=["SpO2 dropped to 91% at 14:30 — supplemental O2 applied"],
        nurse_notes=[
            NurseNote(time="08:15", text="Patient alert and orientated. Persistent productive cough."),
            NurseNote(time="14:30", text="SpO2 fell to 91%. Applied 4L O2. Dr. Patel informed. IV antibiotics delayed, cannula re-sited at 14:50."),
        ],
    )


@pytest.fixture
def watch_patient() -> Patient:
    """A patient that should be classified as WATCH."""
    return Patient(
        patient_id="pt_002",
        name="James Thornton",
        age=58,
        bed="4B",
        diagnosis="Post-operative day 2 — laparoscopic appendectomy",
        admission_date="2025-03-09",
        vitals=Vitals(hr=98, bp="118/74", temp=37.8, rr=18, spo2=96, last_updated="14:00"),
        medications=[
            Medication(name="Oxycodone 5mg", route="Oral", due="14:00", status="given"),
            Medication(name="Metoclopramide 10mg", route="IV", due="18:00", status="pending"),
        ],
        pending_orders=["Wound check and dressing change due at 18:00"],
        alerts=[],
        nurse_notes=[
            NurseNote(time="13:30", text="Patient reported nausea — not vomiting. Ondansetron PRN administered. Pain 4/10."),
        ],
    )


@pytest.fixture
def stable_patient() -> Patient:
    """A patient that should be classified as STABLE."""
    return Patient(
        patient_id="pt_003",
        name="Dorothy Chen",
        age=45,
        bed="4C",
        diagnosis="Hypertensive urgency — BP now controlled",
        admission_date="2025-03-10",
        vitals=Vitals(hr=72, bp="138/86", temp=36.8, rr=16, spo2=98, last_updated="13:30"),
        medications=[
            Medication(name="Amlodipine 10mg", route="Oral", due="08:00", status="given"),
            Medication(name="Ramipril 5mg",    route="Oral", due="08:00", status="given"),
        ],
        pending_orders=["Discharge planning — social work referral in progress"],
        alerts=[],
        nurse_notes=[
            NurseNote(time="08:30", text="All morning medications administered. BP improving."),
        ],
    )


@pytest.fixture
def valid_gpt_response_critical() -> str:
    """A well-formed JSON string as GPT-4o would return for a critical patient."""
    return '''{
        "patient_id": "pt_001",
        "priority": "critical",
        "situation": "Margaret O'Brien, 72F, Bed 4A, admitted with community-acquired pneumonia. Currently on 4L supplemental O2 following SpO2 drop to 91% at 14:30. IV antibiotics delayed due to cannula issue; cannula re-sited at 14:50 and dose now pending.",
        "background": "Admitted 09/03 with confirmed CAP. Paracetamol 1g given at 12:00 with mild symptomatic improvement. Chest X-ray repeat ordered but not yet performed. Blood cultures ordered but not yet collected.",
        "assessment": "Patient clinically unstable. HR 108 bpm, SpO2 91% on supplemental O2, Temp 38.6 °C, RR 22/min. Delayed antibiotic administration adds urgency. Awaiting medical review from Dr. Patel.",
        "recommendation": "1. Administer Amoxicillin-Clavulanate 1.2g IV immediately — cannula patent as of 14:50.\\n2. Chase chest X-ray porter — ordered but not completed.\\n3. Collect blood cultures x2 before next antibiotic dose.\\n4. Monitor SpO2 continuously — escalate if drops below 90% on current O2.\\n5. Ensure Dr. Patel review occurs at start of incoming shift.",
        "flags": [
            "SpO2 91% — supplemental O2 in use",
            "IV antibiotic dose pending (delayed)",
            "Chest X-ray not yet completed",
            "Blood cultures not yet collected",
            "Awaiting medical review (Dr. Patel)"
        ]
    }'''


@pytest.fixture
def valid_gpt_response_stable() -> str:
    """A well-formed JSON string as GPT-4o would return for a stable patient."""
    return '''{
        "patient_id": "pt_003",
        "priority": "stable",
        "situation": "Dorothy Chen, 45F, Bed 4C, admitted with hypertensive urgency. BP now controlled at 138/86 mmHg following antihypertensive therapy.",
        "background": "Admitted 10/03. All three antihypertensive medications administered at 08:00. BP improved from 142/90 at 08:00 to 138/86 by 13:30. Patient calm, no acute complaints.",
        "assessment": "Patient clinically stable. Vitals within acceptable range. BP responding to current medication regimen. Discharge pending social work review.",
        "recommendation": "1. Confirm social work review has occurred before considering discharge.\\n2. Ensure patient has been educated on home BP monitoring (documented as done this shift).\\n3. No urgent clinical actions required.",
        "flags": [
            "Discharge pending social work review"
        ]
    }'''
