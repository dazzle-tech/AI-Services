# SepsisSentinel -- Clinical AI Sepsis Early Detection

A modular REST API service for AI-powered sepsis early detection.
Analyses 24-hour patient time-series data using GPT-4o and returns a
comprehensive sepsis risk assessment including qSOFA, SIRS, SOFA scores,
organ dysfunction mapping, and probabilistic 24-hour forecasts.

---

## Project Structure

```
Sepsis Early Detection/
  main.py                   FastAPI entry point (python main.py)
  .env                      Environment config (API key, etc.)
  .env.example              Template for .env
  requirements.txt          Python dependencies
  output_schema.json        JSON schema for analysis output
  context.txt               Clinical research context
  sample_data/              Sample patient JSON files (3 patients)
  postman/                  Ready-to-import Postman collection/environment
  app/
    core/config.py           Settings via pydantic-settings
    ai/prompts.py            System and user prompt builders
    ai/client.py             OpenAI API client with retry logic
    models/schemas.py        Pydantic request/response models
    services/sepsis_service.py  Analysis pipeline orchestration
    api/routes.py            REST API endpoints
  tests/
    test_routes.py           Automated endpoint tests
```

---

## Quick Start

### 1. Create and activate a virtual environment

```powershell
cd "c:\Users\jirie\Documents\Sepsis Early Detection"
python -m venv venv
.\venv\Scripts\activate
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure environment

Copy `.env.example` to `.env` and set your OpenAI API key:

```powershell
copy .env.example .env
```

Then edit `.env` and replace `sk-your-key-here` with your actual key.

### 4. Start the server

```powershell
python main.py
```

The server starts at **http://localhost:8023**.

---

## API Endpoints

### Root -- Service Info

```
GET http://localhost:8023/
```

Returns service name, version, and docs URL.

---

### Health Check

```
GET http://localhost:8023/api/v1/health
```

Returns service health status and OpenAI configuration info.

---

### List Available Patients

```
GET http://localhost:8023/api/v1/patients
```

Returns the 3 built-in sample patient resources with summary metadata.

---

### Get One Sample Patient

```
GET http://localhost:8023/api/v1/patients/1
```

Returns the full sample patient JSON payload, including `patient_info`
and `hourly_data`.

---

### Create an Analysis for a Sample Patient

```
POST http://localhost:8023/api/v1/patients/1/analyses
```

Runs the model against one of the built-in sample patients and returns a
full sepsis risk assessment.

---

### Create an Analysis from Custom Patient Data

```
POST http://localhost:8023/api/v1/analyses
Content-Type: application/json
```

**Request body:**

```json
{
  "patient_data": {
    "patient_info": {
      "name": "Jane Doe",
      "age": 58,
      "gender": "Female",
      "weight_kg": 65,
      "height_cm": 165,
      "bmi": 23.9,
      "blood_type": "A+",
      "admission_reason": "Suspected UTI",
      "comorbidities": ["Diabetes"],
      "allergies": ["Penicillin"]
    },
    "hourly_data": []
  }
}
```

**Response:** Full sepsis risk assessment JSON including:
- Patient snapshot
- Status summary (qSOFA, SIRS, SOFA scores)
- Current vitals and labs with trends
- Timeline analysis
- Organ dysfunction assessment
- Watchlist of concerning parameters
- 24-hour forecast
- Sepsis probability
- Recommended clinical actions
- Clinical decision support flags

---

### Legacy Compatibility Endpoint

```
POST http://localhost:8023/api/v1/analyze
```

This route still works for older clients, but new integrations should
prefer the REST-style `POST /patients/{patient_id}/analyses` and
`POST /analyses` endpoints.

---

## Interactive API Docs (Swagger UI)

Once the server is running, open your browser to:

```
http://localhost:8023/docs
```

This provides an interactive Swagger UI where you can test all endpoints
directly in the browser without Postman.

---

## Testing with Postman

1. Start the server: `python main.py`
2. Import the collection:
   `postman/SepsisSentinel.postman_collection.json`
3. Import the local environment:
   `postman/SepsisSentinel.local.postman_environment.json`
4. Confirm the `baseUrl` variable is set to `http://localhost:8023`
5. Run any of the included requests:
   - `Root`
   - `Health`
   - `List Patients`
   - `Get Patient By ID`
   - `Create Sample Patient Analysis`
   - `Create Custom Analysis`
   - `Legacy Analyze`

---

## Running Automated Tests

```powershell
.\venv\Scripts\activate
pytest tests/ -v
```

---

## Environment Variables

| Variable             | Required | Default   | Description                        |
|----------------------|----------|-----------|------------------------------------|
| OPENAI_API_KEY       | Yes      | --        | Your OpenAI API key                |
| OPENAI_MODEL         | No       | qwen3:1.7b | OpenAI model to use               |
| OPENAI_TEMPERATURE   | No       | 0.2       | Model temperature (0.0 - 1.0)     |
| OPENAI_TIMEOUT       | No       | 120       | API call timeout in seconds        |
| API_HOST             | No       | 0.0.0.0   | Server bind host                   |
| API_PORT             | No       | 8023      | Server bind port                   |
| API_RELOAD           | No       | false     | Auto-reload on code changes        |
