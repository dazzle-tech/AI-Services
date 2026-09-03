# Medication Test Orders Validation Service

AI-powered service for validating medications and diagnostic test orders against patient data to identify potential safety concerns, contraindications, and conflicts.

## Overview

This service provides three main validation capabilities:
1. **Medication Validation** - Validates medications against patient data for drug interactions, contraindications, dosing issues
2. **Test Validation** - Validates diagnostic test orders for appropriateness, contraindications, and sequencing issues
3. **Allergy-Drug Validation** - Checks proposed drugs against documented allergies (patient details optional)

## Architecture

```
medication-test-orders-validation/
├── main.py                          # FastAPI application entry point
├── config.py                        # Configuration and settings
├── models/
│   └── schemas.py                   # Pydantic data models
├── services/
│   ├── medication_tests_validation_service.py  # Core validation logic
│   └── sample_clinical_data.py      # Sample data for testing
├── tests/                           # Test files
└── requirements.txt                 # Python dependencies
```

## Features

### Medication Validation
- Drug-drug interactions
- Drug-disease interactions
- Age-appropriate dosing
- Gender-specific considerations
- Contraindications based on diagnosis
- Dosage appropriateness
- Duration concerns
- Duplicate therapy detection

### Test Validation
- Test appropriateness for age and gender
- Contraindications based on patient condition
- Redundant or duplicate tests
- Test sequencing issues
- Patient preparation requirements
- Diagnostic value assessment
- Priority and urgency appropriateness

## Installation

### 1. Install Dependencies

```bash
cd medication-test-orders-validation
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```env
# OpenAI cloud default. Override this only if you want to route the same
# client to another OpenAI-compatible provider such as Ollama.
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=qwen3:1.7b
OPENAI_TEMPERATURE=0.2
OPENAI_MAX_TOKENS=2000
HOST=0.0.0.0
PORT=8006
DEBUG=False
```

## Running the Service

### Development Mode

```bash
python main.py
```

The service will start on **http://localhost:8006**

### Production Mode

```bash
uvicorn main:app --host 0.0.0.0 --port 8006
```

## API Endpoints

### 1. Root Endpoint
```
GET /
```
Returns service information and available endpoints.

### 2. Health Check
```
GET /health
```
Returns service health status.

### 3. Medication Validation
```
POST /api/v1/validate/medication
```

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
    "primaryDiagnosis": "I20.0,Unstable angina"
  },
  "listOfDiagnosis": [
    {
      "type": "Encounter Diagnosis",
      "value": "I20.0,Unstable angina"
    }
  ],
  "medications": [
    "Medication Name:  | Active Ingredients: Acetylsalicylic acid - 100 mg"
  ]
}
```

`Medication Name:` may be empty. `Active Ingredients:` is the required part of
each medication string.

**Response:**
```json
{
  "quick_summary": {
    "overall_status": "CAUTION",
    "top_priority": "Age-inappropriate dosing detected"
  },
  "detailed_validations": [
    {
      "item": "Aspirin 100mg",
      "severity": "moderate",
      "issue": "Dosing may need adjustment for pediatric patient",
      "recommendation": "Consult pediatric dosing guidelines",
      "evidence": "Standard adult dose; pediatric adjustment required"
    }
  ],
  "recommended_alternatives": [],
  "confidence_score": 0.92,
  "timestamp": "2025-12-24T10:30:00.000Z"
}
```

### 4. Test Validation
```
POST /api/v1/validate/tests
```

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
    "primaryDiagnosis": "I20.0,Unstable angina"
  },
  "listOfDiagnosis": [
    {
      "type": "Encounter Diagnosis",
      "value": "I20.0,Unstable angina"
    }
  ],
  "tests": [
    "Order Type: Laboratory | Test Name: Troponin | Internal Code: TROP00 | Status: New"
  ]
}
```

**Response:** Same structure as medication validation.

### 5. Allergy-Drug Validation
```
POST /api/v1/validate/allergy-drugs
```

Checks proposed drugs against documented allergies and for drug-drug interactions between listed drugs. `patient` is optional and may be omitted or empty. At least one drug is required. Allergies may be empty.

**Request Body:**
```json
{
  "patient": {
    "fullName": "John Doe",
    "gender": "Male",
    "dob": "2022-02-02",
    "chiefComplaint": "Chest pain",
    "primaryDiagnosis": "I20.0,Unstable angina"
  },
  "allergies": [
    {
      "allergy_description": "Penicillin",
      "allergy_type_description": "Drug"
    }
  ],
  "drugs": [
    {
      "drug_name": "Penicillin"
    }
  ]
}
```

Minimal request (no patient):
```json
{
  "allergies": [
    {
      "allergy_description": "Penicillin",
      "allergy_type_description": "Drug"
    }
  ],
  "drugs": [
    {
      "drug_name": "Penicillin"
    }
  ]
}
```

Drug-drug interaction example (no allergies):
```json
{
  "allergies": [],
  "drugs": [
    { "drug_name": "Clarithromycin" },
    { "drug_name": "Rosuvastatin" }
  ]
}
```

**Response:** Same structure as medication validation.

## Validation Status Levels

- **SAFE** - No issues detected, safe to proceed
- **CAUTION** - Some concerns identified, review recommended
- **CONTRAINDICATED** - Significant safety concerns, should not proceed

## Severity Levels

- **critical** - Immediate safety concern
- **high** - Significant safety concern
- **moderate** - Moderate concern requiring attention
- **low** - Minor concern
- **info** - Informational note

## Testing

### Run Tests

```bash
pytest tests/
```

### Test Individual Components

```bash
# Test medication validation
pytest tests/medication_validation_test.py

# Test test validation
pytest tests/tests_validation_test.py
```

## Configuration

Key settings in `config.py`:

- `OPENAI_BASE_URL` - Base URL for the OpenAI cloud endpoint by default; override it only for another OpenAI-compatible server
- `OPENAI_API_KEY` - OpenAI API key used when calling the default OpenAI cloud endpoint
- `OPENAI_MODEL` - Model to use (default: `qwen3:1.7b`)
- `OPENAI_TEMPERATURE` - Model temperature (default: 0.2)
- `OPENAI_MAX_TOKENS` - Max tokens in response (default: 2000)
- `VALIDATION_CONFIDENCE_THRESHOLD` - Minimum confidence score (default: 0.7)
- `MAX_RETRY_ATTEMPTS` - Retry attempts for API calls (default: 3)
- `REQUEST_TIMEOUT` - Request timeout in seconds (default: 60)

## API Documentation

Once running, access:
- **Swagger UI**: http://localhost:8005/docs
- **ReDoc**: http://localhost:8005/redoc

## Example Use Cases

1. **Pre-prescription Validation**: Validate medications before prescribing
2. **Order Review**: Review test orders for appropriateness
3. **Safety Checking**: Check for drug interactions and contraindications
4. **Dosing Validation**: Verify age-appropriate dosing
5. **Duplicate Detection**: Identify duplicate medications or tests

## Error Handling

The service includes comprehensive error handling:
- Validation errors return 400 Bad Request
- Service errors return 500 Internal Server Error
- All errors include detailed error messages

## Logging

Logs are output to console with INFO level by default. Includes:
- Request processing
- OpenAI API calls
- Validation results
- Errors and warnings

The manual test scripts under `tests/` call the configured backend directly.
With the defaults above, they use the OpenAI cloud API. To switch to a local
OpenAI-compatible backend such as Ollama, set `OPENAI_BASE_URL` and choose a
model name available on that server.

## CI workflow (.github/workflows/medication-test-order-val-ci.yml)
----

**Ready to use!** Start the service and begin validating medications and tests. 🚀




