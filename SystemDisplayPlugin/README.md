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

All requests are currently unauthenticated (API key disabled).

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/reshape` | Map `stage1_output` onto one or more views (`views` / `view_ids`; aliases `view_decoder` / `view_id` still work) |
| POST | `/api/v1/decoders` | Register / upsert a `ViewDecoder` for reuse |
| GET | `/api/v1/decoders/{view_id}` | Retrieve a stored decoder |
| GET | `/api/v1/health` | Service health |

## Example

```bash
curl -X POST http://localhost:8031/api/v1/reshape \
  -H "Content-Type: application/json" \
  -d '{
    "stage1_output": {
      "subjective": "Patient reports a 3-day frontal headache without fever.",
      "objective": "Alert, afebrile.",
      "assessment": "Tension-type headache.",
      "plan": "Ibuprofen as needed. Follow up in two weeks.",
      "vitals": {
        "temperature_c": "36.8",
        "spo2_pct": "98",
        "bp_systolic": "122",
        "bp_diastolic": "78",
        "pulse_rate": "72",
        "pain_score": "2",
        "resp_rate": "16"
      },
      "measurements": {
        "weight_kg": "71.4",
        "height_cm": "168",
        "note": "Weight after shoes removed."
      }
    },
    "context": "appointment",
    "purpose": "soap_note",
    "view_ids": ["soap_note", "vital_signs", "measurement"]
  }'
```

Seeded at startup: `soap_note`, `vital_signs`, `measurement`. Response is `{ "results": [ { "view_id", "data", "warnings" } ] }`. A view that cannot resolve required fields is reported in `results` with warnings; the request is 422 only if **no** view succeeds.

`view_decoder` / `view_id` aliases still accept a single inline decoder or stored id.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_PORT` | `8031` | Server port |
| `API_KEY` | — | Unused while auth is disabled |
| `OPENAI_API_KEY` | — | OpenAI API key (non-direct transforms) |
| `MAPPING_MODEL` | `gpt-4o` | Model for summarize/concat/split/extract |
| `USE_LLM_STUB` | `false` | Deterministic offline transforms |
| `DATABASE_URL` | — | Postgres connection for stored decoders |
| `REDIS_URL` | — | Health-check ping only |

Celery, MinIO, and transcription are intentionally omitted: this service has no audio pipeline.
