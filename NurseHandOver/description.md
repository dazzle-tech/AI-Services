# NurseHandOver

## Overview

NurseHandOver generates structured **SBAR** (Situation, Background, Assessment, Recommendation)
handoff summaries at shift change. It takes a patient's chart data, synthesizes the clinical
picture, and returns a standardized, priority-ranked summary for the incoming nurse.

The service is **stateless**. It owns no shift state, no patient records, and no database —
the caller supplies the chart and receives the summary. In this repo the caller is the agent,
which reads the chart from the shared `hospital.db` and stores the nurse-confirmed handoff back
there. That keeps `hospital.db` the single source of truth, in line with the rest of the stack.

> The original standalone version shipped a React frontend and a JSON flat-file store
> (`patients.json` / `runtime_store.json`) with `/shift/load`, `/notes/add`, `/handoff/confirm`,
> and `GET /handoff/{shift_id}`. All of that was removed on integration: the dashboard is the UI,
> and `hospital.db` is the store. See "Integration" below for where each of those went.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI 0.115.0, Python 3.11, Uvicorn |
| AI | Shared OpenAI-compatible endpoint (`OPENAI_BASE_URL` / `OPENAI_MODEL`, default `gpt-4o`) |
| Data Validation | Pydantic v2 |
| Persistence | None — stateless by design |

---

## API

Runs on **port 8028** (`PORT` env var). All endpoints consume and return JSON.

### `GET /health`
Health check. Returns service name, version, active model, and timestamp. Used by the compose
health-gate and the agent's tool registry.

### `POST /summary/generate`

The core AI pipeline. Generates SBAR summaries for every patient in the request, concurrently.

**Request:**
```json
{
  "shift_id": "shift-1005-day",
  "nurse_id": "nurse_sarah_mitchell",
  "patients": [ /* one or more Patient objects — see Data Models */ ]
}
```

**Response:** one result per patient.

```json
{
  "shift_id": "shift-1005-day",
  "status": "draft",
  "generated_at": "2026-07-29T19:00:00Z",
  "results": [
    {
      "patient_id": "1005",
      "success": true,
      "summary": {
        "patient_id": "1005",
        "priority": "critical",
        "situation": "59-year-old male with diabetic ketoacidosis…",
        "background": "Admitted with glucose 386…",
        "assessment": "Clinical deterioration with hypoxia and fever…",
        "recommendation": "1. Administer insulin sliding scale…\n2. Repeat glucose…",
        "flags": ["Insulin dose pending", "SpO2 91% on room air"],
        "generated_at": "2026-07-29T19:00:00Z"
      }
    }
  ]
}
```

**Priority classification** is rule-based and enforced in the system prompt:
- **Critical:** SpO2 < 92%, HR > 110 or < 50, Temp > 38.5 °C, RR > 22, SBP < 90, unresolved alert,
  or acute deterioration
- **Watch:** Borderline vitals, pending non-urgent orders, or nurse-noted concern
- **Stable:** All vitals within normal range, no unresolved alerts, medications on schedule

Failures are isolated per patient — one LLM error never aborts the batch; it comes back as
`success: false` with an `error` message for that patient only.

---

### AI Pipeline

For each patient, in this order:

```
build_user_prompt()     →  Assembles chart data + shift notes into structured text
get_system_prompt()     →  Static SBAR rules, priority criteria, output JSON schema
call_gpt()              →  LLM call (temp 0.2, max_tokens 700, response_format json_object)
parse_and_validate()    →  Parses raw JSON → validates against the SBARSummary schema
```

The model is instructed to return **valid JSON only**, never infer details absent from the chart,
and use clinical language throughout. `response_format: json_object` enforces JSON at the
protocol level. Retries on `RateLimitError` with exponential backoff (max 2).

Missing chart values are rendered as `not recorded` rather than `None`, so an absent vital can
never be mistaken for a real reading.

---

### Data Models

```
Patient  (patient_id + name required; everything else optional)
  ├── patient_id, name, age, bed, diagnosis, admission_date
  ├── Vitals (hr, bp, temp, rr, spo2, last_updated)
  ├── Medication[] (name, route, due, status)
  ├── pending_orders: str[]
  ├── alerts: str[]
  └── nurse_notes: NurseNote[] (time, text)

SBARSummary
  ├── patient_id
  ├── priority: "critical" | "watch" | "stable"
  ├── situation, background, assessment, recommendation
  ├── flags: str[]
  └── generated_at: datetime
```

---

### Configuration

Supplied by docker-compose from the **root** `.env` (`x-llm-env`); see `.env.example` for
standalone runs.

```env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=            # blank = api.openai.com
OPENAI_MODEL=gpt-4o
TEMPERATURE=0.2
MAX_TOKENS=700
MAX_RETRIES=2
PORT=8028
```

---

### Testing

```bash
cd NurseHandOver && python -m pytest tests -q
```

- `test_gpt_service.py` — mocked LLM responses (no API calls)
- `test_prompt_builder.py` — prompt assembly correctness
- `test_summary_parser.py` — JSON parsing and schema validation

---

## Integration

The dashboard's **Nursing / ICU → Handoff** tab drives the workflow. It never calls this
service directly; everything goes through the agent so that chart reads and record writes stay
on `hospital.db`.

```
Nurse selects an ICU patient      →  dashboard
Generates the handoff             →  POST /agent/nursing/handoff/generate
                                     └→ agent builds the chart from hospital.db
                                     └→ POST http://nursehandover:8028/summary/generate
Reviews & edits the draft         →  review modal (client-side)
Confirms the handoff              →  POST /agent/nursing/handoff/confirm
                                     └→ INSERT into demo_nursing_handoffs
Incoming nurse retrieves it       →  GET  /agent/nursing/handoff
```

Where the removed endpoints went:

| Original endpoint | Now |
|---|---|
| `POST /shift/load` | Agent reads `hospital.db` (`demo_admission`, `demo_vitals`, `demo_medications`, …) |
| `POST /notes/add` | Optional `notes` field on `/agent/nursing/handoff/generate` |
| `POST /handoff/confirm` | `POST /agent/nursing/handoff/confirm` → `demo_nursing_handoffs` |
| `GET /handoff/{shift_id}` | `GET /agent/nursing/handoff` |
| React frontend (:5173) | The dashboard's Handoff tab |
