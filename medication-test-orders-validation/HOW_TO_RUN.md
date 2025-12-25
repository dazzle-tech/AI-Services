# How to Run Medication Test Orders Validation Service

## 🚀 Quick Start

### Step 1: Install Dependencies

```bash
cd medication-test-orders-validation
pip install -r requirements.txt
```

### Step 2: Configure Environment

Create `.env` file:

```env
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_MODEL=gpt-4o
OPENAI_TEMPERATURE=0.2
HOST=0.0.0.0
PORT=8005
DEBUG=False
```

### Step 3: Run the Service

```bash
python main.py
```

Service starts on: **http://localhost:8005**

## ✅ Verify It's Running

1. **Browser**: http://localhost:8005
2. **API Docs**: http://localhost:8005/docs
3. **Health**: http://localhost:8005/health

## 🧪 Test in Postman

### Medication Validation

**URL:** `http://localhost:8005/api/v1/validate/medication`  
**Method:** POST  
**Headers:** `Content-Type: application/json`

**Body:**
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
    "Medication Name: Aspirin | Active Ingredients: Acetylsalicylic acid - 100 mg"
  ]
}
```

### Test Validation

**URL:** `http://localhost:8005/api/v1/validate/tests`  
**Method:** POST  
**Headers:** `Content-Type: application/json`

**Body:**
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
    "Order Type: Laboratory | Test Name: Troponin | Internal Code: TROP00 | Status: New"
  ]
}
```

## 📋 Service Structure

- **main.py** - FastAPI app with endpoints
- **config.py** - Settings and configuration
- **models/schemas.py** - Data models (Patient, Encounter, Request/Response schemas)
- **services/medication_tests_validation_service.py** - Validation logic using OpenAI

## 🔧 Configuration

Edit `config.py` or set environment variables:
- `OPENAI_API_KEY` (required)
- `OPENAI_MODEL` (default: gpt-4o)
- `PORT` (default: 8005)
- `HOST` (default: 0.0.0.0)

## 🛑 Stop Service

Press `Ctrl + C` in terminal.

---

**That's it!** The service is ready to validate medications and tests. 🎉

