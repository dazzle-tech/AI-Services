# NurseHandOver

Stateless SBAR handoff service. Each API call takes **one patient**; the service returns a structured Situation / Background / Assessment / Recommendation summary with a rule-based priority (`critical` | `watch` | `stable`). It does **not** store charts, shifts, or confirmed handoffs.

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
| POST | `/summary/generate` | Generate an SBAR draft for one patient |

Unauthenticated. No request headers. One patient per call. Send `handover_nurse` (the signed-in nurse). The response is only `formatted_text`, `generated_by_ai_for`, and `generated_at`.

## Example

```bash
curl -X POST http://localhost:8028/summary/generate \
  -d '{
    "handover_nurse": "Sarah Mitchell",
    "patient_data": {
      "allergies": [{"allergy_description": "Penicillin", "allergy_type_description": "Drug"}],
      "warnings": [{"virus_description": "MRSA colonisation", "type": "Infection Control"}],
      "last_hospital_course": "Admitted 28/08 via ED with community-acquired pneumonia.",
      "past_medical_history": [
        {"record_type": "Blood Transfusion", "record_description": "Yes, 16/05/2025"}
      ],
      "diagnosis": [
        {"diagnosis_type": "Principal", "diagnosis_code": "J18.9", "diagnosis_description": "Pneumonia, unspecified organism"}
      ],
      "vital_signs": {
        "pulse_rate": "88",
        "bp_systolic": "128",
        "bp_diastolic": "76",
        "temperature_c": "37.4",
        "respiratory_rate": "18",
        "spo2_pct": "95",
        "pain_score": "3"
      },
      "pending_operations": [
        {"operation_name": "Bronchoscopy", "requested_date": "2026-09-04T09:00:00"}
      ]
    }
  }'
```

Priority cues used in the system prompt:

- **Critical:** SpO2 < 92%, HR > 110 or < 50, Temp > 38.5 °C, RR > 22, SBP < 90, unresolved alert, or acute deterioration
- **Watch:** Borderline vitals, pending non-urgent orders, or nurse-noted concern
- **Stable:** Vitals in range, no unresolved alerts, medications on schedule

Required: `handover_nurse` and `patient_data`. No request headers.

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
