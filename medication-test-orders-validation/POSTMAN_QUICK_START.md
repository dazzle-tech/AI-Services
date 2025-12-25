# 🚀 Quick Start Guide - Testing in Postman

## Step 1: Start the Service

Open a terminal/command prompt and run:

```bash
cd C:\Users\User\Desktop\AI-Services\medication-test-orders-validation
python main.py
```

**Wait for the message:** `Application startup complete` or `Uvicorn running on...`

The service will run on: **http://localhost:8000**

---

## Step 2: Import Postman Collection

### Option A: Import Collection File (Recommended)

1. Open **Postman**
2. Click **Import** button (top left)
3. Click **Upload Files**
4. Select: `postman_collection.json` from the project folder
5. Click **Import**

You'll now have all test requests ready to use!

### Option B: Manual Setup

If you prefer to create requests manually, follow the examples below.

---

## Step 3: Test the Endpoints

### ✅ Test 1: Health Check (Quick Test)

1. **Method:** `GET`
2. **URL:** `http://localhost:8000/health`
3. **Headers:** None needed
4. Click **Send**

**Expected Response:**
```json
{
  "status": "healthy",
  "services": {
    "medication_validation": "operational",
    "test_validation": "operational"
  }
}
```

---

### ✅ Test 2: Medication Validation

1. **Method:** `POST`
2. **URL:** `http://localhost:8000/api/v1/validate/medication`
3. **Headers:**
   - Key: `Content-Type`
   - Value: `application/json`
4. **Body:** Select `raw` and `JSON`, then paste:

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

5. Click **Send**

**Expected Response:**
- Status: `200 OK`
- Response includes:
  - `quick_summary.overall_status` (SAFE/CAUTION/CONTRAINDICATED)
  - `detailed_validations` array with findings
  - `confidence_score`
  - `recommended_alternatives` (if any)

---

### ✅ Test 3: Test Validation

1. **Method:** `POST`
2. **URL:** `http://localhost:8000/api/v1/validate/tests`
3. **Headers:**
   - Key: `Content-Type`
   - Value: `application/json`
4. **Body:** Select `raw` and `JSON`, then paste:

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

5. Click **Send**

---

## 📋 All Available Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service information |
| `/health` | GET | Health check |
| `/api/v1/validate/medication` | POST | Validate medications |
| `/api/v1/validate/tests` | POST | Validate diagnostic tests |
| `/docs` | GET | Swagger UI documentation |

---

## 🎯 Test Scenarios Included in Collection

The imported collection includes:

1. **Health Check** - Verify service is running
2. **Root Endpoint** - Get service info
3. **Medication Validation - Sample 1** - Drug interaction test (Aspirin + Warfarin)
4. **Medication Validation - Age Inappropriate** - Pediatric safety test
5. **Medication Validation - Safe Medication** - Normal case
6. **Test Validation - Sample 1** - Basic test validation
7. **Test Validation - Multiple Tests** - Duplicate test detection

---

## 🔍 Understanding the Response

### Response Structure:
```json
{
  "quick_summary": {
    "overall_status": "SAFE|CAUTION|CONTRAINDICATED",
    "top_priority": "Most critical issue description"
  },
  "detailed_validations": [
    {
      "item": "Medication/Test name",
      "severity": "critical|high|moderate|low|info",
      "issue": "Problem description",
      "recommendation": "What to do",
      "evidence": "Clinical reasoning"
    }
  ],
  "recommended_alternatives": [
    {
      "original_item": "Original medication/test",
      "alternative": "Safer alternative",
      "rationale": "Why it's better"
    }
  ],
  "confidence_score": 0.95,
  "timestamp": "2025-12-24T10:30:00.000Z"
}
```

### Status Levels:
- **SAFE** - No issues detected
- **CAUTION** - Some concerns, review recommended
- **CONTRAINDICATED** - Significant safety concerns

### Severity Levels:
- **critical** - Immediate safety concern
- **high** - Significant concern
- **moderate** - Moderate concern
- **low** - Minor concern
- **info** - Informational note

---

## ⚠️ Troubleshooting

### Service Not Starting?
- Check if port 8000 is already in use
- Verify `.env` file has `OPENAI_API_KEY` set
- Check Python dependencies: `pip install -r requirements.txt`

### Getting 500 Error?
- Check service logs in terminal
- Verify API key is valid
- Ensure request JSON is valid

### Getting Connection Refused?
- Make sure service is running (`python main.py`)
- Verify URL is `http://localhost:8000` (not 8005)
- Check firewall settings

### Slow Response?
- Normal! AI validation takes 10-30 seconds
- Increase timeout in Postman settings if needed

---

## 📝 Quick Reference

**Service URL:** `http://localhost:8000`  
**Health Check:** `GET http://localhost:8000/health`  
**API Docs:** `http://localhost:8000/docs` (Swagger UI)

**Start Command:**
```bash
cd C:\Users\User\Desktop\AI-Services\medication-test-orders-validation
python main.py
```

---

**Ready to test!** 🎉 Import the collection and start sending requests!

