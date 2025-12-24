# Testing Guide for Clinical Summary Service

## Quick Start

### Install Test Dependencies
```bash
pip install -r requirements.txt
```

### Run All Tests
```bash
pytest
```

## REST API Endpoints

The service provides the following REST API endpoints:

### 1. Root Endpoint
- **GET** `/`
- Returns service information
- Example: `curl http://localhost:8003/`

### 2. Health Check
- **GET** `/api/v1/health`
- Returns service health status
- Example: `curl http://localhost:8003/api/v1/health`

### 3. Generate Summary
- **POST** `/api/v1/summarize`
- Generates clinical summary from patient data
- Example:
```bash
curl -X POST http://localhost:8003/api/v1/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "patient_data": {
      "Age": "45 years",
      "Gender": "Male",
      "Diagnosis": "Type 2 Diabetes",
      "Symptoms": ["Polyuria", "Polydipsia"],
      "Medications": ["Metformin 500mg BID"]
    }
  }'
```

### 4. API Documentation
- **GET** `/docs` - Swagger UI
- **GET** `/redoc` - ReDoc documentation
- **GET** `/openapi.json` - OpenAPI schema

## Test Structure

### Unit Tests (`tests/unit/`)
- `test_schemas.py` - Schema validation tests (15+ tests)
- `test_prompts.py` - Prompt generation tests (8+ tests)

### Integration Tests (`tests/integration/`)
- `test_api.py` - REST API endpoint tests (10+ tests)
- `test_service.py` - Service layer tests (5+ tests)

### Test Fixtures (`tests/fixtures/`)
- `sample_data.py` - Reusable test data

## Running Specific Tests

### Run Unit Tests Only
```bash
pytest tests/unit/
```

### Run Integration Tests Only
```bash
pytest tests/integration/
```

### Run Specific Test File
```bash
pytest tests/unit/test_schemas.py
```

### Run Specific Test
```bash
pytest tests/unit/test_schemas.py::TestPatientDataInput::test_valid_minimal_data
```

### Run with Coverage
```bash
pytest --cov=app --cov-report=html --cov-report=term-missing
```

### Run with Verbose Output
```bash
pytest -v
```

### Run with Markers
```bash
pytest -m unit          # Unit tests only
pytest -m integration    # Integration tests only
```

## Test Coverage

The test suite covers:
- ✅ Schema validation (required fields, empty values, data types)
- ✅ Prompt generation (system prompts, user prompts, data formatting)
- ✅ REST API endpoints (all endpoints, error handling)
- ✅ Service layer (request processing, response generation)
- ✅ Error handling (validation errors, API errors)
- ✅ Edge cases (missing fields, empty values, optional fields)

## Manual Testing

### Start the Server
```bash
python main.py
```

### Test with cURL

**Health Check:**
```bash
curl http://localhost:8003/api/v1/health
```

**Generate Summary:**
```bash
curl -X POST http://localhost:8003/api/v1/summarize \
  -H "Content-Type: application/json" \
  -d @test_request.json
```

**View API Docs:**
Open browser to: `http://localhost:8003/docs`

### Test with Python

```python
import requests

# Health check
response = requests.get("http://localhost:8003/api/v1/health")
print(response.json())

# Generate summary
data = {
    "patient_data": {
        "Age": "45 years",
        "Gender": "Male",
        "Diagnosis": "Type 2 Diabetes",
        "Symptoms": ["Polyuria", "Polydipsia"],
        "Medications": ["Metformin 500mg BID"]
    }
}
response = requests.post("http://localhost:8003/api/v1/summarize", json=data)
print(response.json())
```

## Continuous Integration

Tests are designed to run in CI/CD pipelines:
- No external dependencies (OpenAI API is mocked)
- Fast execution (< 5 seconds)
- Deterministic results
- No side effects

## Troubleshooting

### Tests Fail with Import Errors
```bash
# Make sure you're in the project root
cd summarization_service
pytest
```

### Tests Fail with Module Not Found
```bash
# Install dependencies
pip install -r requirements.txt
```

### OpenAI API Key Errors
Tests use mocked API calls, so no real API key is needed. If you see API key errors, check `tests/conftest.py` for mocked environment variables.

