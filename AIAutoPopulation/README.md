# AI Auto-Population Service

A production-ready backend service for extracting structured medical data from clinician free-text input, with cross-checking against patient records.

## Features

- **Structured Data Extraction**: Extracts medical data (diagnoses, medications, vitals, procedures, etc.) from free-text clinical documentation
- **Safety First**: Never hallucinates medical data, flags uncertainties, and identifies contradictions
- **Audit Trail**: Complete source trace for all extracted data
- **Validation**: Strict JSON validation and field checking
- **Decision Support Only**: Provides structured data extraction, no autonomous medical decisions

## Architecture

```
app/
├── api/              # FastAPI routes and endpoints
├── services/         # Business logic layer
├── models/           # Pydantic schemas
├── ai/              # AI client and prompts
└── core/            # Configuration and constants
```

## Setup

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Configure environment**:
```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

3. **Run the service**:
```bash
python main.py
```

Or with uvicorn directly:
```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`

## Testing

### Quick Test
1. Start server: `python main.py`
2. Run test: `python test_v2_api.py`

### Postman
1. Import `AI_Auto_Population.postman_collection.json`
2. Use `test_request_v2.json` as request body
3. Endpoint: `POST http://localhost:8000/api/v1/auto-populate/v2`

See `TESTING_GUIDE.md` for detailed instructions.

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API Endpoints

### POST `/api/v1/auto-populate` (V1 - Legacy)

Legacy endpoint for backward compatibility.

### POST `/api/v1/auto-populate/v2` (V2 - Recommended)

New clean API contract with organized request/response structure.

Extracts structured medical data from free-text input.

**V2 Request Body** (Recommended):
```json
{
  "request_id": "req_123",
  "task_type": "auto_population",
  "languages": {
    "input": "en",
    "output": "en"
  },
  "inputs": {
    "user_text": "Patient presents with chest pain...",
    "onsite": {
      "patient_record_id": "pr_456",
      "is_deidentified": true,
      "patient_data": {
        "medications": [...],
        "allergies": [...],
        "vitals": {...}
      }
    }
  },
  "requested_outputs": {
    "include_summary": true,
    "include_structured_fields": true,
    "include_vitals": true
  }
}
```

**V2 Response**:
```json
{
  "request_id": "req_123",
  "task_type": "auto_population",
  "outputs": {
    "summary": "65-year-old male with acute chest pain...",
    "structured_fields": {
      "chief_complaint": "...",
      "diagnosis": [...],
      "medications": [...]
    }
  },
  "quality": {
    "uncertainty_flags": [...],
    "contradictions": [...],
    "warnings": [...]
  },
  "trace": {
    "source_trace": [...]
  },
  "metadata": {
    "model_used": "qwen3:1.7b",
    "processing_timestamp": "...",
    "schema_version": "auto_population.v1"
  }
}
```

## Safety Features

1. **No Hallucination**: Only extracts data explicitly mentioned in input
2. **Uncertainty Flags**: Flags fields where evidence is insufficient
3. **Contradiction Detection**: Identifies mismatches between user text and patient records
4. **Source Trace**: Tracks origin of every extracted field

## Development

This service is designed for extensibility. Future tasks (discharge QA, guideline checks, recommendations) can be added following the same patterns.

## CI workflow (.github/workflows/auto-populate-ci.yml)

## License

[Add your license here]

