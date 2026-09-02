# NurseHandOver

Stateless SBAR handoff service. The caller sends one or more patient charts; the service returns a structured Situation / Background / Assessment / Recommendation summary per patient, with a rule-based priority (`critical` | `watch` | `stable`). It does **not** store charts, shifts, or confirmed handoffs.

API: http://localhost:8028  
Docs: http://localhost:8028/docs  
Health: http://localhost:8028/health  
Postman: `postman/NurseHandOver.postman_collection.json`

## Quick start

```bash
cd NurseHandOver
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set OPENAI_API_KEY in .env

python main.py
# or: uvicorn main:app --reload --port 8028
```

```bash
curl http://localhost:8028/health
```

### Docker

```bash
docker build -t nursehandover .
docker run -p 8028:8028 --env-file .env nursehandover
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness: service name, version, model, timestamp |
| POST | `/summary/generate` | Generate SBAR drafts for every patient in the body |

Unauthenticated. Failures are isolated per patient: one LLM error returns `success: false` for that patient and does not abort the batch. Response `status` is always `draft` — review and persistence belong to the caller.

## Example

```bash
curl -X POST http://localhost:8028/summary/generate \
  -H "Content-Type: application/json" \
  -d '{
    "shift_id": "shift-1005-day",
    "nurse_id": "nurse_sarah_mitchell",
    "patients": [
      {
        "patient_id": "pt_001",
        "name": "Margaret O'\''Brien",
        "age": 72,
        "bed": "4A",
        "diagnosis": "Community-acquired pneumonia",
        "admission_date": "2025-03-09",
        "vitals": {
          "hr": 108,
          "bp": "94/61",
          "temp": 38.6,
          "rr": 22,
          "spo2": 91,
          "last_updated": "14:45"
        },
        "medications": [
          {
            "name": "Amoxicillin-Clavulanate 1.2g IV",
            "route": "IV",
            "due": "15:00",
            "status": "pending"
          }
        ],
        "pending_orders": ["Repeat chest X-ray — awaiting porter"],
        "alerts": ["SpO2 dropped to 91% at 14:30"],
        "nurse_notes": [
          {"time": "14:30", "text": "SpO2 fell to 91%. Applied 4L O2. Dr. Patel informed."}
        ]
      }
    ]
  }'
```

Priority cues used in the system prompt:

- **Critical:** SpO2 < 92%, HR > 110 or < 50, Temp > 38.5 °C, RR > 22, SBP < 90, unresolved alert, or acute deterioration
- **Watch:** Borderline vitals, pending non-urgent orders, or nurse-noted concern
- **Stable:** Vitals in range, no unresolved alerts, medications on schedule

Required on each patient: `patient_id`, `name`. Everything else is optional.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | `8028` | Server port |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `OPENAI_BASE_URL` | — | Leave blank for api.openai.com |
| `OPENAI_MODEL` | `gpt-4o` | Chat model |
| `TEMPERATURE` | `0.2` | Generation temperature |
| `MAX_TOKENS` | `700` | Max completion tokens |
| `MAX_RETRIES` | `2` | Rate-limit retries |

## Tests

```bash
python -m pytest tests -q
```

LLM calls are mocked; no live OpenAI key is required for the suite.
