# Lab Result Interpreter Service

AI-powered lab result interpretation support service using OpenAI GPT-4. This service receives lab values and optional patient context, then returns a structured interpretation of abnormal findings, relevant trends, clinically meaningful patterns, and suggested clinical follow-up considerations.

**Important:** This service provides interpretation support only and does not diagnose independently.

## Overview

- **Purpose:** Interpret lab results with optional patient context; detect patterns and trends; suggest follow-up considerations.
- **Architecture:** Layered design (API → Service → AI Client → Prompts) consistent with SummarizationService.
- **Output:** Structured JSON with `severity`, `key_findings`, `patterns`, `trends`, `follow_up_considerations`, and disclaimer.

## Quick Start

### Run Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env and add your OpenAI API key

# 3. Run the server
python main.py

# 4. Test the API
curl http://localhost:8003/api/v1/health
```

### Run with Docker

```bash
# Build and run
docker-compose up --build

# Or build image only
docker build -t lab-result-interpreter-service .
docker run -p 8003:8003 -e OPENAI_API_KEY=your-key lab-result-interpreter-service
```

## Configuration

| Variable             | Description                    | Default   |
| -------------------- | ------------------------------ | --------- |
| `OPENAI_API_KEY`     | OpenAI API key (required)      | -         |
| `OPENAI_MODEL`       | Model name                     | `qwen3:1.7b`  |
| `OPENAI_TEMPERATURE` | Temperature                    | `0.2`     |
| `OPENAI_MAX_TOKENS`  | Max completion tokens          | `1500`    |
| `API_PORT`           | Server port                    | `8003`    |
| `LOG_LEVEL`          | Logging level                  | `INFO`    |

## API Endpoints

### `POST /api/v1/interpret-labs`

Interpret lab results with optional patient context and historical comparison.

**Example Request:**

```json
{
  "request_id": "req-lab-001",
  "patient_context": {
    "patient_id": "P-1001",
    "age": 58,
    "sex": "male",
    "known_conditions": ["Type 2 Diabetes", "Hypertension"],
    "medications": ["Metformin", "Lisinopril"],
    "clinical_context": "Admitted with fever and shortness of breath"
  },
  "lab_results": [
    {
      "name": "WBC",
      "value": "18.2",
      "unit": "10^9/L",
      "reference_range": "4.0-11.0",
      "flag": "high",
      "timestamp": "2026-03-16T08:00:00Z"
    }
  ],
  "historical_lab_results": [
    {
      "name": "Creatinine",
      "value": "1.0",
      "unit": "mg/dL",
      "flag": "normal",
      "timestamp": "2026-03-14T08:00:00Z"
    },
    {
      "name": "Creatinine",
      "value": "1.8",
      "unit": "mg/dL",
      "flag": "high",
      "timestamp": "2026-03-16T08:00:00Z"
    }
  ]
}
```

**Example Response:**

```json
{
  "request_id": "req-lab-001",
  "interpretation": {
    "severity": "high",
    "key_findings": [
      "WBC is elevated",
      "CRP is markedly elevated"
    ],
    "patterns": [
      {
        "label": "possible_infection_or_inflammation",
        "reason": "Combination of elevated WBC and CRP suggests significant inflammatory or infectious activity."
      }
    ],
    "trends": [
      {
        "lab_name": "Creatinine",
        "direction": "rising",
        "summary": "Creatinine increased from 1.0 to 1.8 over 48 hours."
      }
    ],
    "follow_up_considerations": [
      "Correlate with vital signs and clinical exam",
      "Review cultures and infection workup"
    ],
    "disclaimer": "This output is interpretation support and not a diagnosis."
  },
  "summary": "Lab interpretation generated successfully.",
  "processing_metadata": {
    "model": "qwen3:1.7b",
    "timestamp": "2026-03-20T12:00:00.000000",
    "lab_result_count": 1,
    "trend_count": 1
  }
}
```

### `GET /api/v1/health`

Health check and OpenAI configuration status.

## Postman Collection

Import the collection for manual testing:

1. Open Postman.
2. **Import** → Choose `postman/LabResultInterpreterService.postman_collection.json`.
3. Set the `baseUrl` variable to `http://localhost:8003` (default).
4. Run the requests: Health Check, Interpret Labs (Minimal), Interpret Labs (Full Example), Interpret Labs (Invalid Payload).

The collection includes test scripts to validate status codes and response structure.

## Testing

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit/

# Run integration tests only
pytest tests/integration/
```

## Safety

- **Interpretation support only:** Does not diagnose. Uses cautious language (possible, may suggest, compatible with).
- **No treatment orders:** Does not recommend treatment plans as orders.
- **Disclaimer:** Every response includes a disclaimer that output is interpretation support and not a diagnosis.
- **Traceability:** Raw values, units, ranges, and timestamps are preserved in structured output.

## Disclaimer

This is an AI-powered interpretation support tool. All output should be reviewed by qualified healthcare professionals. AI systems can make errors—always verify accuracy before clinical use.
