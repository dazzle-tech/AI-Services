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
  "request_id": "d54bef27-142d-4cef-ada8-5bdc2099c9e9",
  "patient_context": {
    "age": 10,
    "sex": "FEMALE",
    "known_conditions": [
      {
        "name": "Other specified bursopathies (M71.8)",
        "date": "2026-04-20"
      },
      {
        "name": "Calcium deposit in bursa (M71.4)",
        "date": "2026-04-29"
      },
      {
        "name": "Calcium deposit in bursa (M71.4)",
        "date": "2026-05-04"
      },
      {
        "name": "Calcium deposit in bursa (M71.4)",
        "date": "2026-05-04"
      }
    ],
    "clinical_context": "Other specified bursopathies (M71.8), Calcium deposit in bursa (M71.4)"
  },
  "lab_results": [
    {
      "name": "CBC2",
      "value": "Days",
      "unit": "",
      "reference_range": "Hours",
      "flag": "abnormal_marker",
      "timestamp": "2026-04-20T13:31:12.799330Z"
    },
    {
      "name": "CBC1",
      "value": "25.00",
      "unit": "Ratio",
      "reference_range": "5.0 - 10.0",
      "flag": "critical_upper",
      "timestamp": "2026-04-20T13:31:06.908451Z"
    },
    {
      "name": "CBC2",
      "value": "Hours",
      "unit": "",
      "reference_range": "Hours",
      "flag": "normal_marker",
      "timestamp": "2026-05-03T07:16:54.051299Z"
    },
    {
      "name": "CBC1",
      "value": "4.00",
      "unit": "Ratio",
      "reference_range": "5.0 - 10.0",
      "flag": "lower_limit",
      "timestamp": "2026-05-03T07:16:51.752292Z"
    },
    {
      "name": "فحص دم",
      "value": "8.00",
      "unit": "INR",
      "reference_range": " ",
      "flag": "unknown",
      "timestamp": "2026-06-10T13:24:19.517946Z"
    },
    {
      "name": "cc",
      "value": "8.00",
      "unit": "INR",
      "reference_range": " ",
      "flag": "unknown",
      "timestamp": "2026-06-10T13:24:15.933330Z"
    }
  ],
  "medications": [
    {
      "name": "nexium",
      "start_date": "2026-07-07T21:00:00.000Z",
      "end_date": null
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

## CI workflow (.github/workflows/lab-result-ci.yml)

## Disclaimer

This is an AI-powered interpretation support tool. All output should be reviewed by qualified healthcare professionals. AI systems can make errors—always verify accuracy before clinical use.
