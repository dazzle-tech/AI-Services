# ORDisplayPlugin

Stage-2 field mapper for **ORScribe** JSON. Reshapes existing structured output (timeline, medications, instrument counts, WHO checklist, roles) onto target OR views. It does **not** regenerate clinical content and does **not** ingest audio.

This is the OR counterpart of SystemDisplayPlugin (which maps ConvoScribe SOAP / clinic charts). Paste the body of ORScribe `POST /api/v1/analyze` or `GET /api/v1/cases/{id}` as `stage1_output`.

API: http://localhost:8032  
Docs: http://localhost:8032/docs  
Health: http://localhost:8032/api/v1/health

## Quick start (Docker)

```bash
cd ORDisplayPlugin
cp .env.example .env
docker compose up --build
```

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

set DATABASE_URL=postgresql://ordisplay:ordisplay@localhost:5436/ordisplay
set USE_LLM_STUB=true

python main.py
```

All requests are unauthenticated (no API key headers).

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/reshape` | Map ORScribe `stage1_output` onto one or more views |
| POST | `/api/v1/decoders` | Register / upsert a `ViewDecoder` |
| GET | `/api/v1/decoders/{view_id}` | Retrieve a stored decoder |
| GET | `/api/v1/health` | Service health |

Seeded at startup: `or_timeline`, `or_medications`, `or_counts`, `or_checklist`, `or_roles`.

## Example

```bash
curl -X POST http://localhost:8032/api/v1/reshape \
  -H "Content-Type: application/json" \
  -d '{
    "context": "operating_room",
    "purpose": "timeline",
    "view_ids": ["or_timeline", "or_medications", "or_counts", "or_checklist", "or_roles"],
    "stage1_output": {
      "procedure_type": "laparoscopic cholecystectomy",
      "needs_review": false,
      "role_map": {
        "SPEAKER_00": {"role": "surgeon", "confidence": "high", "needs_review": false},
        "SPEAKER_01": {"role": "anesthetist", "confidence": "high", "needs_review": false}
      },
      "role_reasoning": "Speaker 0 makes incision; speaker 1 reports vitals and drugs.",
      "timeline": {
        "events": [
          {"timestamp": "00:00:22", "type": "incision", "speaker_role": "surgeon", "description": "Incision made"}
        ],
        "medications_administered": [
          {"timestamp": "00:01:10", "drug": "propofol", "dose": "100 mg", "administered_by_role": "anesthetist"}
        ],
        "instrument_counts": [
          {"timestamp": "00:14:02", "type": "sponge_count", "result": "correct", "reported_by_role": "nurse"}
        ]
      },
      "checklist": {
        "sign_in": {"completed": true, "items_confirmed": ["identity", "site marked"], "items_missing": []},
        "time_out": {"completed": true, "items_confirmed": ["team introductions"], "items_missing": []},
        "sign_out": {"completed": true, "items_confirmed": ["procedure recorded"], "items_missing": []}
      }
    }
  }'
```

Case records from ORScribe (`medications`, `instrument_counts`, `checklist_result`) are flattened to the same paths before mapping.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_PORT` | `8032` | Server port |
| `OPENAI_API_KEY` | — | OpenAI API key (non-direct transforms) |
| `MAPPING_MODEL` | `gpt-4o` | Model for summarize/concat/split/extract |
| `USE_LLM_STUB` | `false` | Deterministic offline transforms |
| `DATABASE_URL` | — | Postgres for stored decoders |

## Testing

```bash
pytest
```

## Postman

Import `postman/ORDisplayPlugin.postman_collection.json`. Set `baseUrl` to `http://localhost:8032`.
