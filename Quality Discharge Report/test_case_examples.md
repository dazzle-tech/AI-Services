# Test Case Examples

This document provides ready-to-use test cases for the Discharge QA Service.

## Test Case 1: Complete, Well-Structured Report ✅

**Scenario:** Perfect discharge report with all required sections and fields.

**Input:**
```json
{
  "discharge_report": "DISCHARGE SUMMARY\n\nPatient Information:\nAge: 65\nSex: Male\nAdmission Date: 2024-01-15\nDischarge Date: 2024-01-18\n\nChief Complaint:\nChest pain\n\nHospital Course:\nAdmitted for chest pain. Ruled out MI.\n\nDiagnoses:\nPrimary: Chest pain\n\nMedications on Discharge:\n- Aspirin 81mg PO daily\n\nAllergies:\nNo known allergies\n\nReturn Precautions:\nReturn if chest pain worsens\n\nDischarge Disposition:\nHome",
  "patient_record": {
    "age": 65,
    "sex": "Male",
    "diagnoses": ["Chest pain"]
  },
  "onsite_docs": []
}
```

**Expected Result:**
- Score: 90-100
- Minimal errors
- All required sections present

---

## Test Case 2: Missing Required Fields ❌

**Scenario:** Report missing critical information (sex, discharge medications, return precautions).

**Input:**
```json
{
  "discharge_report": "DISCHARGE SUMMARY\n\nPatient Information:\nAge: 65\n\nDiagnoses:\nPrimary: MI",
  "patient_record": {
    "age": 65,
    "sex": "Male",
    "diagnoses": ["MI"]
  },
  "onsite_docs": []
}
```

**Expected Result:**
- Score: 60-80
- Missing items: sex, discharge_medications, return_precautions
- Completeness errors

---

## Test Case 3: Medication Inconsistency ⚠️

**Scenario:** Discharge report lists different medications than patient record.

**Input:**
```json
{
  "discharge_report": "DISCHARGE SUMMARY\n\nPatient Information:\nAge: 65\nSex: Male\n\nDiagnoses:\nPrimary: MI\n\nMedications on Discharge:\n- Warfarin 5mg PO daily\n\nAllergies:\nNo known allergies\n\nDischarge Disposition:\nHome",
  "patient_record": {
    "age": 65,
    "sex": "Male",
    "diagnoses": ["MI"],
    "medications": [
      {"name": "Aspirin", "dose": "81mg", "frequency": "daily"},
      {"name": "Clopidogrel", "dose": "75mg", "frequency": "daily"}
    ]
  },
  "onsite_docs": [
    {
      "doc_id": "DOC-001",
      "doc_type": "progress_note",
      "timestamp": "2024-01-16T10:00:00Z",
      "department": "Cardiology",
      "content": "Patient on Aspirin and Clopidogrel",
      "is_deidentified": true
    }
  ]
}
```

**Expected Result:**
- Inconsistencies detected
- Medication conflict flagged
- Lower score due to inconsistency

---

## Test Case 4: Allergy Conflict 🚨

**Scenario:** Medication prescribed that patient is allergic to (CRITICAL SAFETY ISSUE).

**Input:**
```json
{
  "discharge_report": "DISCHARGE SUMMARY\n\nPatient Information:\nAge: 65\nSex: Male\n\nDiagnoses:\nPrimary: Pneumonia\n\nMedications on Discharge:\n- Penicillin 500mg PO TID\n\nAllergies:\nPenicillin - causes severe rash\n\nDischarge Disposition:\nHome",
  "patient_record": {
    "age": 65,
    "sex": "Male",
    "diagnoses": ["Pneumonia"],
    "allergies": ["Penicillin"]
  },
  "onsite_docs": []
}
```

**Expected Result:**
- **CRITICAL SAFETY ERROR**
- Score capped at 50
- Allergy/medication conflict flagged
- High severity error

---

## Test Case 5: Missing Return Precautions ⚠️

**Scenario:** High-risk case (chest pain) without return precautions.

**Input:**
```json
{
  "discharge_report": "DISCHARGE SUMMARY\n\nPatient Information:\nAge: 65\nSex: Male\n\nChief Complaint:\nChest pain\n\nHospital Course:\nAdmitted with chest pain\n\nDiagnoses:\nPrimary: Chest pain\n\nMedications on Discharge:\n- Aspirin 81mg PO daily\n\nAllergies:\nNo known allergies\n\nDischarge Disposition:\nHome",
  "patient_record": {
    "age": 65,
    "sex": "Male",
    "diagnoses": ["Chest pain"]
  },
  "onsite_docs": []
}
```

**Expected Result:**
- Safety error for missing return precautions
- Missing item flagged
- Lower score

---

## Test Case 6: Incomplete Medication Information ⚠️

**Scenario:** Medications missing dose or frequency information.

**Input:**
```json
{
  "discharge_report": "DISCHARGE SUMMARY\n\nPatient Information:\nAge: 65\nSex: Male\n\nDiagnoses:\nPrimary: Hypertension\n\nMedications on Discharge:\n- Aspirin\n- Metoprolol 25mg\n\nAllergies:\nNo known allergies\n\nDischarge Disposition:\nHome",
  "patient_record": {
    "age": 65,
    "sex": "Male",
    "diagnoses": ["Hypertension"]
  },
  "onsite_docs": []
}
```

**Expected Result:**
- Safety/completeness errors
- Missing dose or frequency flagged
- Medication instructions incomplete

---

## Test Case 7: With Report Template 📋

**Scenario:** Using template to validate structure.

**Input:**
```json
{
  "discharge_report": "DISCHARGE SUMMARY\n\nPatient Information:\nAge: 65\nSex: Male\n\nDiagnoses:\nPrimary: MI\n\nMedications:\n- Aspirin 81mg PO daily\n\nDischarge Disposition:\nHome",
  "patient_record": {
    "age": 65,
    "sex": "Male",
    "diagnoses": ["MI"]
  },
  "onsite_docs": [],
  "report_template": {
    "sections": [
      {
        "name": "patient_info",
        "required": true,
        "fields": ["age", "sex", "admission_date", "discharge_date"]
      },
      {
        "name": "encounter_summary",
        "required": true,
        "fields": ["chief_complaint", "hospital_course"]
      },
      {
        "name": "diagnoses",
        "required": true,
        "fields": ["primary_diagnosis"]
      },
      {
        "name": "medications",
        "required": true,
        "fields": ["discharge_medications"]
      },
      {
        "name": "disposition",
        "required": true,
        "fields": ["discharge_disposition"]
      }
    ]
  }
}
```

**Expected Result:**
- Template-based validation
- Missing template-required fields identified
- Structure validated against template

---

## Running the Test Cases

### Using pytest:
```bash
pytest tests/test_cases/test_complete_qa.py -v
```

### Using specific test:
```bash
pytest tests/test_cases/test_complete_qa.py::TestCompleteQA::test_case_1_complete_report -v
```

### Using Postman:
1. Copy the JSON input from any test case
2. Paste into Postman request body
3. Send to `http://localhost:8000/discharge/qa/direct`
4. Compare results with expected outcomes

---

## Test Case Summary

| Test Case | Focus | Expected Score | Key Checks |
|-----------|-------|----------------|------------|
| 1. Complete Report | All sections present | 90-100 | Completeness |
| 2. Missing Fields | Required fields missing | 60-80 | Missing items |
| 3. Medication Inconsistency | Report vs record mismatch | 70-85 | Inconsistencies |
| 4. Allergy Conflict | Safety issue | ≤50 | Critical safety error |
| 5. Missing Precautions | High-risk case | 70-85 | Safety error |
| 6. Incomplete Meds | Missing dose/frequency | 75-90 | Safety/completeness |
| 7. With Template | Template validation | 70-95 | Template compliance |

---

## Custom Test Cases

To create your own test case:

1. Define the scenario (what you're testing)
2. Create discharge report text
3. Create patient_record with relevant data
4. Add onsite_docs if testing consistency
5. Include report_template if testing structure
6. Run through QA service
7. Verify expected results match actual results

Example:
```python
result = service.perform_qa(
    discharge_report="Your report text here",
    patient_record={"age": 65, "sex": "Male", ...},
    onsite_docs=[],
    report_template=None,
    quality_rules=quality_rules
)

assert result["overall_score"] >= expected_score
assert len(result["errors"]) <= max_errors
```

