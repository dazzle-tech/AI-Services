# SystemDisplayPlugin

Stage-2 field mapper for ORScribe and ConvoScribe JSON. Reshapes existing structured output (SOAP note, timeline, summary, checklist, …) onto a target view schema. It does **not** regenerate clinical content.

API: http://localhost:8031  
Docs: http://localhost:8031/docs  
Health: http://localhost:8031/api/v1/health

## Quick start (Docker)

```bash
cd SystemDisplayPlugin
cp .env.example .env
docker compose up --build
```

## Local development

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export DATABASE_URL=postgresql://systemdisplay:systemdisplay@localhost:5435/systemdisplay
export USE_LLM_STUB=true

python main.py
# or: uvicorn main:app --reload --port 8031
```

All requests require header `X-API-Key`.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/reshape` | Map `stage1_output` using an inline `view_decoder` or stored `view_id` |
| POST | `/api/v1/decoders` | Register / upsert a `ViewDecoder` for reuse |
| GET | `/api/v1/decoders/{view_id}` | Retrieve a stored decoder |
| GET | `/api/v1/health` | Service health |

## Example

```bash
curl -X POST http://localhost:8031/api/v1/reshape \
  -H "X-API-Key: change-me-to-a-secure-random-key" \
  -H "Content-Type: application/json" \
  -d '{
    "stage1_output": {
      "subjective": "Patient reports a 3-day frontal headache without fever.",
      "objective": "Alert, afebrile.",
      "assessment": "Tension-type headache.",
      "plan": "Ibuprofen as needed. Follow up in two weeks.",
      "medications_mentioned": ["ibuprofen"],
      "follow_up": "two weeks",
      "flags": []
    },
    "context": "appointment",
    "purpose": "soap_note",
    "view_decoder": {
      "view_id": "ehr_soap_card",
      "view_name": "EHR SOAP card",
      "fields": [
        {"field_name": "hpi", "field_type": "string", "source_path": "subjective"},
        {"field_name": "dx", "field_type": "string", "source_path": "assessment"}
      ]
    }
  }'
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_PORT` | `8031` | Server port |
| `API_KEY` | — | Request authentication |
| `OPENAI_API_KEY` | — | OpenAI API key (non-direct transforms) |
| `MAPPING_MODEL` | `gpt-4o` | Model for summarize/concat/split/extract |
| `USE_LLM_STUB` | `false` | Deterministic offline transforms |
| `DATABASE_URL` | — | Postgres connection for stored decoders |
| `REDIS_URL` | — | Health-check ping only |

Celery, MinIO, and transcription are intentionally omitted: this service has no audio pipeline.
