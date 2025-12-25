# Postman Testing Guide - Medication Test Orders Validation

## 🚀 Quick Setup

### Step 1: Start Service
```bash
cd medication-test-orders-validation
python main.py
```

Service runs on: **http://localhost:8005**

## 📋 API Endpoints

### 1. Medication Validation

**URL:** `http://localhost:8005/api/v1/validate/medication`  
**Method:** POST  
**Headers:** `Content-Type: application/json`

**Request Body:**
```json
{
  "patient": {
    "mrn": "1000",
    "fullName": "John Doe",
    "gender": "Male",
    "dob": "2022-02-02"
  },
  "encounter": {
    "visitId": "160",
    "visitType": "Urgent Visit",
    "plannedStartDate": "2025-12-24",
    "chiefComplaint": "Chest pain",
    "patientAge": "3y 10m 22d",
    "diagnosis": "I20.0,Unstable angina"
  },
  "complain": "Chest pain",
  "diagnosis": {
    "type": "Encounter Diagnosis",
    "value": "I20.0,Unstable angina"
  },
  "medications": [
    "Medication Name: Aspirin | Active Ingredients: Acetylsalicylic acid - 100 mg",
    "Medication Name: Warfarin | Active Ingredients: Warfarin sodium - 5 mg"
  ]
}
```

### 2. Test Validation

**URL:** `http://localhost:8005/api/v1/validate/tests`  
**Method:** POST  
**Headers:** `Content-Type: application/json`

**Request Body:**
```json
{
  "patient": {
    "mrn": "1000",
    "fullName": "John Doe",
    "gender": "Male",
    "dob": "2022-02-02"
  },
  "encounter": {
    "visitId": "160",
    "visitType": "Urgent Visit",
    "plannedStartDate": "2025-12-24",
    "chiefComplaint": "Chest pain",
    "patientAge": "3y 10m 22d",
    "diagnosis": "I20.0,Unstable angina"
  },
  "complain": "Chest pain",
  "diagnosis": {
    "type": "Encounter Diagnosis",
    "value": "I20.0,Unstable angina"
  },
  "tests": [
    "Order Type: Laboratory | Test Name: Troponin | Internal Code: TROP00 | Status: New",
    "Order Type: Laboratory | Test Name: Complete Blood Count | Internal Code: CBC00 | Status: New"
  ]
}
```

## ✅ Expected Response Format

```json
{
  "quick_summary": {
    "overall_status": "CAUTION",
    "top_priority": "Drug interaction detected between Aspirin and Warfarin"
  },
  "detailed_validations": [
    {
      "item": "Aspirin 100mg",
      "severity": "high",
      "issue": "Increased bleeding risk when combined with Warfarin",
      "recommendation": "Monitor INR closely, consider dose adjustment",
      "evidence": "Aspirin potentiates Warfarin's anticoagulant effects"
    }
  ],
  "recommended_alternatives": [
    {
      "original_item": "Aspirin 100mg",
      "alternative": "Consider clopidogrel if antiplatelet needed",
      "rationale": "Lower bleeding risk when combined with Warfarin"
    }
  ],
  "confidence_score": 0.95,
  "timestamp": "2025-12-24T10:30:00.000Z"
}
```

## 🎯 Test Scenarios

### Test 1: Safe Medication
```json
{
  "patient": {"mrn": "1001", "fullName": "Jane Smith", "gender": "Female", "dob": "1980-01-01"},
  "encounter": {"visitId": "161", "visitType": "Routine", "plannedStartDate": "2025-12-24", "chiefComplaint": "Headache", "patientAge": "45y", "diagnosis": "G44.1,Tension headache"},
  "complain": "Headache",
  "diagnosis": {"type": "Encounter Diagnosis", "value": "G44.1,Tension headache"},
  "medications": ["Medication Name: Ibuprofen | Active Ingredients: Ibuprofen - 400 mg"]
}
```

### Test 2: Age-Inappropriate Medication
```json
{
  "patient": {"mrn": "1002", "fullName": "Baby Doe", "gender": "Male", "dob": "2024-01-01"},
  "encounter": {"visitId": "162", "visitType": "Urgent", "plannedStartDate": "2025-12-24", "chiefComplaint": "Fever", "patientAge": "1y 11m", "diagnosis": "R50.9,Fever"},
  "complain": "Fever",
  "diagnosis": {"type": "Encounter Diagnosis", "value": "R50.9,Fever"},
  "medications": ["Medication Name: Aspirin | Active Ingredients: Acetylsalicylic acid - 325 mg"]
}
```

### Test 3: Multiple Tests
```json
{
  "patient": {"mrn": "1003", "fullName": "Test Patient", "gender": "Female", "dob": "1975-05-15"},
  "encounter": {"visitId": "163", "visitType": "Emergency", "plannedStartDate": "2025-12-24", "chiefComplaint": "Chest pain", "patientAge": "50y 7m", "diagnosis": "I21.9,Acute MI"},
  "complain": "Chest pain",
  "diagnosis": {"type": "Encounter Diagnosis", "value": "I21.9,Acute MI"},
  "tests": [
    "Order Type: Laboratory | Test Name: Troponin | Internal Code: TROP00 | Status: New",
    "Order Type: Laboratory | Test Name: Troponin | Internal Code: TROP00 | Status: New",
    "Order Type: Imaging | Test Name: Chest X-Ray | Internal Code: CXR00 | Status: New"
  ]
}
```

## 🔍 Response Fields Explained

| Field | Description |
|-------|-------------|
| `quick_summary.overall_status` | SAFE, CAUTION, or CONTRAINDICATED |
| `quick_summary.top_priority` | Most critical issue found |
| `detailed_validations` | Array of validation findings |
| `detailed_validations[].item` | Medication or test name |
| `detailed_validations[].severity` | critical, high, moderate, low, info |
| `detailed_validations[].issue` | Description of the problem |
| `detailed_validations[].recommendation` | What to do about it |
| `detailed_validations[].evidence` | Clinical reasoning |
| `recommended_alternatives` | Safer alternatives if available |
| `confidence_score` | 0.0 to 1.0 (how confident the AI is) |
| `timestamp` | When validation was performed |

## 🐛 Troubleshooting

**Error: OPENAI_API_KEY not set**
- Create `.env` file with your API key

**Error: Validation failed**
- Check that all required fields are present
- Verify JSON syntax is correct

**Empty validations**
- Ensure patient data is complete
- Check that medications/tests are properly formatted

---

**Ready to test!** Use the examples above in Postman. 🚀

