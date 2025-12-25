# Sample clinical data for testing

# Sample 1: Pediatric patient with potential medication conflicts
SAMPLE_MEDICATION_REQUEST_1 = {
    "patient": {
        "mrn": "1000",
        "fullName": "Clinic Test test Test",
        "gender": "Male",
        "dob": "2022-02-02"
    },
    "encounter": {
        "visitId": "160",
        "visitType": "Urgent Visit",
        "plannedStartDate": "2025-12-24",
        "chiefComplaint": "testrtest",
        "patientAge": "3y 10m 22d",
        "diagnosis": "A048,Other specified bacterial intestinal infections"
    },
    "complain": "testrtest",
    "diagnosis": {
        "type": "Encounter Diagnosis",
        "value": "A048,Other specified bacterial intestinal infections"
    },
    "medications": [
        "Medication Name: EnoCap | Active Ingredients: Enalapril (C09AA02) - 10 mg | Instructions: tests | Instructions Type: Manual Instructions | Valid Until: 2025-12-02 | Is Chronic: No | Duration: 90 | Duration Type: Months | Maximum Dose: 898 | ICD-10: A8100, Creutzfeldt-Jakob disease, unspecified.",
        "Medication Name: Lopressor | Active Ingredients: Metoprolol (C07AB02) - 50 mg | Instructions Type: Pre-defined Instructions | Valid Until: 2025-12-09 | Is Chronic: No | Duration: 1 | Duration Type: Weeks | Maximum Dose: 98 | ICD-10: A001, Cholera due to Vibrio cholerae 01, biovar eltor."
    ]
}

# Sample 2: Adult patient with cardiac issues
SAMPLE_MEDICATION_REQUEST_2 = {
    "patient": {
        "mrn": "2001",
        "fullName": "Sarah Johnson",
        "gender": "Female",
        "dob": "1965-05-15"
    },
    "encounter": {
        "visitId": "201",
        "visitType": "Follow-up Visit",
        "plannedStartDate": "2025-12-24",
        "chiefComplaint": "Chest pain and shortness of breath",
        "patientAge": "60y 7m 9d",
        "diagnosis": "I20.0,Unstable angina"
    },
    "complain": "Chest pain and shortness of breath",
    "diagnosis": {
        "type": "Encounter Diagnosis",
        "value": "I20.0,Unstable angina"
    },
    "medications": [
        "Medication Name: Aspirin | Active Ingredients: Acetylsalicylic acid - 325 mg | Instructions: Take once daily | Instructions Type: Pre-defined Instructions | Valid Until: 2026-12-24 | Is Chronic: Yes | Duration: 365 | Duration Type: Days | Maximum Dose: 325 | ICD-10: I20.0, Unstable angina",
        "Medication Name: Atorvastatin | Active Ingredients: Atorvastatin (C10AA05) - 40 mg | Instructions: Take once daily at bedtime | Instructions Type: Pre-defined Instructions | Valid Until: 2026-12-24 | Is Chronic: Yes | Duration: 365 | Duration Type: Days | Maximum Dose: 80 | ICD-10: E78.0, Pure hypercholesterolemia",
        "Medication Name: Metoprolol | Active Ingredients: Metoprolol (C07AB02) - 100 mg | Instructions: Take twice daily | Instructions Type: Pre-defined Instructions | Valid Until: 2026-12-24 | Is Chronic: Yes | Duration: 365 | Duration Type: Days | Maximum Dose: 200 | ICD-10: I20.0, Unstable angina"
    ]
}

# Sample 3: Elderly patient with polypharmacy risk
SAMPLE_MEDICATION_REQUEST_3 = {
    "patient": {
        "mrn": "3005",
        "fullName": "Robert Martinez",
        "gender": "Male",
        "dob": "1945-08-22"
    },
    "encounter": {
        "visitId": "305",
        "visitType": "Regular Visit",
        "plannedStartDate": "2025-12-24",
        "chiefComplaint": "Multiple chronic conditions management",
        "patientAge": "80y 4m 2d",
        "diagnosis": "I10,Essential (primary) hypertension;E11.9,Type 2 diabetes mellitus without complications"
    },
    "complain": "Multiple chronic conditions management",
    "diagnosis": {
        "type": "Encounter Diagnosis",
        "value": "I10,Essential (primary) hypertension;E11.9,Type 2 diabetes mellitus without complications"
    },
    "medications": [
        "Medication Name: Warfarin | Active Ingredients: Warfarin (B01AA03) - 5 mg | Instructions: Take once daily | Instructions Type: Pre-defined Instructions | Valid Until: 2026-01-24 | Is Chronic: Yes | Duration: 30 | Duration Type: Days | Maximum Dose: 10 | ICD-10: I48.0, Paroxysmal atrial fibrillation",
        "Medication Name: Aspirin | Active Ingredients: Acetylsalicylic acid - 81 mg | Instructions: Take once daily | Instructions Type: Pre-defined Instructions | Valid Until: 2026-01-24 | Is Chronic: Yes | Duration: 30 | Duration Type: Days | Maximum Dose: 81 | ICD-10: I25.10, Atherosclerotic heart disease",
        "Medication Name: Ibuprofen | Active Ingredients: Ibuprofen (M01AE01) - 600 mg | Instructions: Take as needed for pain | Instructions Type: Manual Instructions | Valid Until: 2025-12-31 | Is Chronic: No | Duration: 7 | Duration Type: Days | Maximum Dose: 2400 | ICD-10: M79.3, Panniculitis unspecified"
    ]
}

# Sample 4: Test validation - comprehensive labs
SAMPLE_TEST_REQUEST_1 = {
    "patient": {
        "mrn": "1000",
        "fullName": "Clinic Test test Test",
        "gender": "Male",
        "dob": "2022-02-02"
    },
    "encounter": {
        "visitId": "160",
        "visitType": "Urgent Visit",
        "plannedStartDate": "2025-12-24",
        "chiefComplaint": "testrtest",
        "patientAge": "3y 10m 22d",
        "diagnosis": "A048,Other specified bacterial intestinal infections"
    },
    "complain": "testrtest",
    "diagnosis": {
        "type": "Encounter Diagnosis",
        "value": "A048,Other specified bacterial intestinal infections"
    },
    "tests": [
        "Order Type: Laboratory | Test Name: Blood Type - RH | Internal Code: BTRH00 | Status: New | Reason: Follow-up of Previously Diagnosed Condition | Priority: Regular",
        "Order Type: Laboratory | Test Name: Blood Type - ABO | Internal Code: BTABO00 | Status: New",
        "Order Type: Laboratory | Test Name: Urinalysis (Routine) | Internal Code: UA00 | Status: New",
        "Order Type: Laboratory | Test Name: ALT/SGPT | Internal Code: ALT00 | Status: New"
    ]
}

# Sample 5: Test validation - cardiac workup
SAMPLE_TEST_REQUEST_2 = {
    "patient": {
        "mrn": "2001",
        "fullName": "Sarah Johnson",
        "gender": "Female",
        "dob": "1965-05-15"
    },
    "encounter": {
        "visitId": "201",
        "visitType": "Emergency Visit",
        "plannedStartDate": "2025-12-24",
        "chiefComplaint": "Severe chest pain radiating to left arm",
        "patientAge": "60y 7m 9d",
        "diagnosis": "I20.0,Unstable angina"
    },
    "complain": "Severe chest pain radiating to left arm",
    "diagnosis": {
        "type": "Encounter Diagnosis",
        "value": "I20.0,Unstable angina"
    },
    "tests": [
        "Order Type: Laboratory | Test Name: Troponin I | Internal Code: TROP00 | Status: New | Reason: Rule out myocardial infarction | Priority: STAT",
        "Order Type: Laboratory | Test Name: CK-MB | Internal Code: CKMB00 | Status: New | Reason: Cardiac enzyme | Priority: STAT",
        "Order Type: Radiology | Test Name: Chest X-Ray | Internal Code: CXR00 | Status: New | Reason: Evaluate cardiac silhouette | Priority: Urgent",
        "Order Type: Cardiology | Test Name: ECG 12-Lead | Internal Code: ECG00 | Status: New | Reason: Evaluate for ischemia | Priority: STAT",
        "Order Type: Laboratory | Test Name: BNP | Internal Code: BNP00 | Status: New | Reason: Evaluate heart failure | Priority: Urgent"
    ]
}

# Sample 6: Test validation - routine prenatal
SAMPLE_TEST_REQUEST_3 = {
    "patient": {
        "mrn": "4010",
        "fullName": "Maria Garcia",
        "gender": "Female",
        "dob": "1995-03-10"
    },
    "encounter": {
        "visitId": "410",
        "visitType": "Prenatal Visit",
        "plannedStartDate": "2025-12-24",
        "chiefComplaint": "First prenatal visit",
        "patientAge": "30y 9m 14d",
        "diagnosis": "Z34.00,Encounter for supervision of normal first pregnancy, unspecified trimester"
    },
    "complain": "First prenatal visit",
    "diagnosis": {
        "type": "Encounter Diagnosis",
        "value": "Z34.00,Encounter for supervision of normal first pregnancy, unspecified trimester"
    },
    "tests": [
        "Order Type: Laboratory | Test Name: Complete Blood Count | Internal Code: CBC00 | Status: New | Reason: Routine prenatal screening | Priority: Regular",
        "Order Type: Laboratory | Test Name: Blood Type and Rh | Internal Code: BTRH00 | Status: New | Reason: Prenatal screening | Priority: Regular",
        "Order Type: Laboratory | Test Name: Rubella Antibody | Internal Code: RUB00 | Status: New | Reason: Immunity status | Priority: Regular",
        "Order Type: Radiology | Test Name: X-Ray Lumbar Spine | Internal Code: XRLS00 | Status: New | Reason: Back pain evaluation | Priority: Regular",
        "Order Type: Laboratory | Test Name: HIV Screening | Internal Code: HIV00 | Status: New | Reason: Routine prenatal screening | Priority: Regular"
    ]
}

# All samples organized by type
MEDICATION_SAMPLES = [
    SAMPLE_MEDICATION_REQUEST_1,
    SAMPLE_MEDICATION_REQUEST_2,
    SAMPLE_MEDICATION_REQUEST_3
]

TEST_SAMPLES = [
    SAMPLE_TEST_REQUEST_1,
    SAMPLE_TEST_REQUEST_2,
    SAMPLE_TEST_REQUEST_3
]