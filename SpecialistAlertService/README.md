# Specialist Alert Service

Specialist Alert Service is a REST API-first FastAPI microservice for clinical decision support. It accepts a full patient record at `POST /api/v1/generate-alerts` and returns grounded, structured alerts for possible specialist consultation triggers, urgent review needs, medication safety issues, abnormal patterns, follow-up gaps, and care coordination concerns.

The public contract is intentionally simple and stateless. Internal orchestration is controlled and deterministic: inspect the record, extract risk signals, generate candidate alerts, validate grounding, deduplicate, rank, and return a normalized response. This service does not replace physician, nursing, or specialist judgment.

## REST API

- `GET /api/v1/health`
- `POST /api/v1/generate-alerts`

### Health Check

```bash
curl http://localhost:8014/api/v1/health
```

Example response:

```json
{
  "status": "healthy",
  "service": "specialist-alert",
  "provider": "openai",
  "openai_configured": true,
  "api_accessible": true,
  "model": "qwen3:1.7b",
  "version": "1.1.0"
}
```

### Generate Alerts

```bash
curl -X POST http://localhost:8014/api/v1/generate-alerts \
  -H "Content-Type: application/json" \
  -d @request.json
```

Example request:

```json
{
  "request_id": "req-alert-001",
  "patient_record": {
    "patient_id": "P-1001",
    "demographics": {
      "age": 58,
      "sex": "male"
    },
    "medications": [
      {
        "name": "Ibuprofen",
        "start_date": "2026-03-14",
        "status": "active"
      }
    ],
    "lab_results": [
      {
        "name": "Creatinine",
        "value": "1.8",
        "unit": "mg/dL",
        "reference_range": "0.7-1.3",
        "flag": "high",
        "date": "2026-03-16"
      }
    ],
    "historical_lab_results": [
      {
        "name": "Creatinine",
        "value": "1.0",
        "unit": "mg/dL",
        "reference_range": "0.7-1.3",
        "flag": "normal",
        "date": "2026-03-14"
      }
    ],
    "notes": [
      {
        "date": "2026-03-16",
        "author": "Dr. Lee",
        "type": "progress_note",
        "text": "Renal function worsened since admission. Monitoring closely."
      }
    ],
    "discharge_follow_up": [
      {
        "specialty": "Nephrology",
        "scheduled": false
      }
    ]
  }
}
```

Example response:

```json
{
  "request_id": "req-alert-001",
  "alerts": [
    {
      "alert_id": "ALT-001",
      "category": "lab_pattern_alert",
      "severity": "high",
      "title": "Possible renal deterioration requiring review",
      "reason": "Creatinine increased from 1.0 to 1.8 over serial results and the note states renal function worsened since admission.",
      "recommended_specialty": "Nephrology",
      "supporting_evidence": [
        "Lab Creatinine 1.8 mg/dL on 2026-03-16 flag high",
        "Lab Creatinine 1.0 mg/dL on 2026-03-14 flag normal",
        "Note progress_note on 2026-03-16: Renal function worsened since admission. Monitoring closely."
      ],
      "suggested_action": "Review renal trend, medication exposure, and determine whether nephrology consultation is needed.",
      "confidence": "high"
    }
  ],
  "summary": "Clinical alerts generated successfully.",
  "processing_metadata": {
    "model": "qwen3:1.7b",
    "timestamp": "2026-03-31T10:00:00",
    "alert_count": 1,
    "input_sections_count": 6,
    "risk_signal_count": 3,
    "candidate_alert_count": 2,
    "validated_alert_count": 1,
    "dropped_alert_count": 1,
    "workflow": [
      "inspect_patient_record",
      "extract_risk_signals",
      "generate_candidate_alerts",
      "validate_grounding",
      "deduplicate_alerts",
      "rank_alerts"
    ],
    "provider": "openai",
    "api_version": "v1"
  }
}
```

## Running Locally

```bash
pip install -r requirements.txt
cp .env.example .env
python main.py
```

The service runs on `http://localhost:8014` by default. Interactive docs are available at `http://localhost:8014/docs`.

## Running With Docker

```bash
docker-compose up --build
```

## Configuration

Environment variables follow the same pattern used by `SummarizationService`.

| Variable | Description | Default |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI API key | required |
| `OPENAI_MODEL` | OpenAI model name | `qwen3:1.7b` |
| `API_PORT` | REST API port | `8014` |
| `LOG_LEVEL` | Application log level | `INFO` |
| `OPENAI_TEMPERATURE` | Model temperature | `0.1` |
| `OPENAI_MAX_TOKENS` | Max completion tokens | `1400` |
| `OPENAI_TIMEOUT` | Request timeout in seconds | `45` |
| `OPENAI_MAX_RETRIES` | Retry count for transient failures | `3` |
| `OPENAI_RETRY_DELAY` | Retry delay in seconds | `1.0` |
| `ENABLE_USAGE_TRACKING` | Token usage logging | `True` |
| `MAX_INPUT_LENGTH` | Max serialized record length | `50000` |

## Testing

```bash
python -m pytest
```

The test suite mirrors the service template style:

- unit tests for prompts, schemas, grounding, deduplication, ranking, and signal extraction
- integration tests for the API, service, orchestrator, and malformed AI output handling
- AI client behavior mocked where external calls would otherwise be required

## Postman

Import [postman/SpecialistAlertService.postman_collection.json](/c:/Users/User/Desktop/AI-Services/SpecialistAlertService/postman/SpecialistAlertService.postman_collection.json).

The collection name is `SpecialistAlertService` and it includes:

- Health Check
- Generate Alerts (Minimal)
- Generate Alerts (Full Example)
- Generate Alerts (Invalid Payload)

Collection variable:

- `baseUrl = http://localhost:8014`

## Safety Notes

- This service is clinical decision support only.
- It does not make final diagnoses or authorize treatment or consultation orders.
- Suggested actions intentionally use cautious language such as `consider`, `review for possible`, and `determine whether consultation is needed`.
- Supporting evidence is preserved to keep alerts traceable back to the input record.
