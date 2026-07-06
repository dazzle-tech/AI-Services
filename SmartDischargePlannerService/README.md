# Smart Discharge Planner Service

AI-powered discharge planning assessment service using OpenAI. Receives discharge-related clinical and operational patient data, then returns a structured discharge readiness assessment, blockers, follow-up considerations, medication reconciliation concerns, and a draft discharge planning summary.

**This service supports discharge planning only—it does not make the final discharge decision.**

## Overview

- **Purpose:** Support discharge planning with structured readiness assessment and blockers
- **Main endpoint:** `POST /api/v1/plan-discharge`
- **Architecture:** FastAPI, layered design (API, Services, AI, Models)
- **AI Provider:** OpenAI GPT-4o

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 3. Run locally
python main.py

# 4. Test health
curl http://localhost:8004/api/v1/health
```

**API Documentation:** http://localhost:8004/docs

## Run with Docker

```bash
# Build and run
docker-compose up --build

# Or build only
docker build -t smart-discharge-planner .
docker run -p 8004:8004 -e OPENAI_API_KEY=sk-your-key smart-discharge-planner
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (required) | - |
| `OPENAI_MODEL` | Model name | `qwen3:1.7b` |
| `OPENAI_TEMPERATURE` | Temperature | `0.2` |
| `OPENAI_MAX_TOKENS` | Max completion tokens | `1500` |
| `API_PORT` | Server port | `8004` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Example Request

```bash
curl -X POST "http://localhost:8004/api/v1/plan-discharge" \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req-001",
    "patient_context": {
      "patient_id": "P-1001",
      "admission_date": "2026-03-10",
      "primary_diagnosis": "Pneumonia",
      "secondary_diagnoses": ["Type 2 Diabetes", "Hypertension"],
      "current_status": "improving"
    },
    "clinical_data": {
      "latest_vitals": [{"name": "temperature", "value": "37.1", "unit": "C"}],
      "pending_tests": [{"name": "blood culture", "status": "pending"}],
      "active_problems": ["Needs home oxygen assessment"],
      "medications_current": ["Amoxicillin", "Metformin"],
      "medications_planned_for_discharge": ["Amoxicillin", "Metformin", "Prednisone"]
    },
    "operational_data": {
      "follow_up_appointments": [{"service": "Pulmonology", "scheduled": false}],
      "patient_education": [
        {"topic": "antibiotic adherence", "completed": true},
        {"topic": "warning signs", "completed": false}
      ],
      "transport_status": "available",
      "home_support": "family_available",
      "equipment_needs": [{"name": "home oxygen", "confirmed": false}]
    }
  }'
```

## Example Response

```json
{
  "request_id": "req-001",
  "discharge_plan": {
    "readiness_status": "needs_review",
    "readiness_reason": "Patient appears clinically improved, but unresolved discharge blockers remain.",
    "blockers": [
      {"category": "pending_test", "title": "Blood culture still pending", "reason": "A pending test may affect discharge readiness."},
      {"category": "follow_up", "title": "Pulmonology follow-up not scheduled", "reason": "No follow-up appointment is documented."}
    ],
    "medication_reconciliation_concerns": [
      "Prednisone appears on the planned discharge list and should be verified."
    ],
    "follow_up_considerations": [
      "Confirm whether home oxygen is required before discharge",
      "Schedule pulmonology follow-up"
    ],
    "draft_discharge_summary": "Patient admitted with pneumonia and has clinically improved...",
    "disclaimer": "This output supports discharge planning and does not replace clinician judgment."
  },
  "summary": "Discharge planning assessment generated successfully.",
  "processing_metadata": {
    "model": "qwen3:1.7b",
    "timestamp": "2026-03-20T12:00:00",
    "blocker_count": 2
  }
}
```

## Postman Collection

1. Open Postman
2. File → Import
3. Select `postman/SmartDischargePlannerService.postman_collection.json`
4. Set `baseUrl` variable to `http://localhost:8004` (default)
5. Run requests; test scripts validate status codes and response structure

## Testing

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit/

# Run integration tests
pytest tests/integration/ -v
```

## Safety & Disclaimer

- This service **supports** discharge planning; it does **not** authorize or make final discharge decisions
- Outputs must be reviewed by qualified clinicians
- Never send real PHI without proper compliance review

---

**Made for better discharge planning workflows**
