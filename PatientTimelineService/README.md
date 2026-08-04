# Patient Timeline Service

AI-powered patient timeline generation service using OpenAI.

## Overview

Patient Timeline Service receives structured and semi-structured medical data and generates a chronological timeline of clinically important events. It is designed for hospital information systems that need a traceable, validated timeline built from diagnoses, medications, labs, procedures, encounters, allergies, vitals, and clinical notes.

Key capabilities:

- Extracts clinically important events from structured data and free-text notes
- Returns a chronological timeline with traceable source fields
- Merges duplicate events and preserves medical terminology and numeric values
- Validates request and response payloads with Pydantic schemas
- Uses OpenAI with retry logic and malformed JSON sanitization
- Includes unit tests, integration tests, Docker assets, and Postman collection

## Project Structure

```text
PatientTimelineService/
  main.py
  requirements.txt
  README.md
  Dockerfile
  docker-compose.yml
  .env.example
  pytest.ini
  postman/
    PatientTimelineService.postman_collection.json
  app/
    api/
      routes.py
    ai/
      client.py
      prompts.py
    core/
      config.py
    models/
      schemas.py
    services/
      timeline_service.py
  tests/
    fixtures/
      sample_data.py
    integration/
      test_api.py
      test_service.py
    unit/
      test_prompts.py
      test_schemas.py
```

## Run Locally

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create your environment file:

```bash
cp .env.example .env
```

3. Add your OpenAI API key to `.env`.

4. Start the service:

```bash
python main.py
```

The API will be available at `http://localhost:8001` and the interactive docs at `http://localhost:8001/docs`.

## Run With Docker

1. Create `.env` from `.env.example` and set `OPENAI_API_KEY`.

2. Build and start the container:

```bash
docker compose up --build
```

The service will be available at `http://localhost:8001`.

## API Endpoints

- `GET /`
- `GET /api/v1/health`
- `POST /api/v1/generate-timeline`

## Example Request

```json
{
  "request_id": "req-123",
  "patient_data": {
    "patient_id": "12345",
    "demographics": {
      "age": "58 years",
      "gender": "Male"
    },
    "diagnoses": [
      {
        "name": "Type 2 Diabetes",
        "date": "2022-05-01"
      },
      {
        "name": "Hypertension",
        "date": "2021-03-10"
      }
    ],
    "medications": [
      {
        "name": "Metformin",
        "start_date": "2022-05-02",
        "end_date": null,
        "status": "active"
      },
      {
        "name": "Insulin",
        "start_date": "2023-11-18",
        "end_date": null,
        "status": "active"
      }
    ],
    "lab_results": [
      {
        "name": "Troponin",
        "value": "0.8",
        "unit": "ng/mL",
        "date": "2026-03-13",
        "flag": "high"
      }
    ],
    "vitals": [
      {
        "name": "BP",
        "value": "160/100",
        "date": "2026-03-12"
      }
    ],
    "procedures": [
      {
        "name": "Coronary angiography",
        "date": "2020-02-15",
        "status": "completed"
      }
    ],
    "encounters": [
      {
        "type": "admission",
        "date": "2026-03-12",
        "reason": "Chest pain"
      }
    ],
    "notes": [
      {
        "date": "2026-03-12",
        "author": "Dr. Smith",
        "type": "admission_note",
        "text": "Patient admitted with chest pain and shortness of breath."
      }
    ],
    "allergies": [
      {
        "name": "Penicillin",
        "date": "2020-01-01"
      }
    ]
  }
}
```

## Example Response

```json
{
  "request_id": "req-123",
  "timeline": [
    {
      "date": "2020-02-15",
      "event_type": "procedure",
      "title": "Coronary angiography performed",
      "description": "Completed coronary angiography procedure.",
      "clinical_importance": "high",
      "source": "procedures"
    },
    {
      "date": "2026-03-12",
      "event_type": "admission",
      "title": "Admitted with chest pain",
      "description": "Hospital admission due to chest pain.",
      "clinical_importance": "high",
      "source": "encounters"
    }
  ],
  "summary": "Chronological timeline generated successfully.",
  "processing_metadata": {
    "model": "qwen3:1.7b",
    "timestamp": "2026-03-23T09:00:00",
    "input_fields_count": 9,
    "timeline_event_count": 2
  }
}
```

## Testing

Run the full test suite:

```bash
pytest
```

Run only unit tests:

```bash
pytest tests/unit
```

Run only integration tests:

```bash
pytest tests/integration
```

The test suite mocks the AI client so the service can be verified without live OpenAI calls.

## Postman Collection

Import `postman/PatientTimelineService.postman_collection.json` into Postman.

Collection variable:

- `baseUrl = http://localhost:8001`

Included requests:

- Health Check
- Generate Timeline (Minimal)
- Generate Timeline (Full Example)
- Generate Timeline (Invalid Payload)

## Configuration

Important environment variables:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `API_PORT`
- `LOG_LEVEL`

Additional optional settings are documented in `.env.example`.

## CI workflow (patient-timeline-ci.yml)

## Notes

- The service never intentionally adds facts that are not present in the input.
- Timeline events are validated with Pydantic before they are returned.
- If the LLM returns malformed JSON, the client sanitizes the output and retries.
- Generated timelines should still be reviewed by qualified clinicians before patient-care use.
