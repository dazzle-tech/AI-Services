# ORScribe

Operating Room conversation intelligence service. Ingests OR audio, identifies surgical team roles, extracts an intraoperative timeline, and verifies WHO Surgical Safety Checklist completion.

Separate from any clinic/outpatient summarizer (e.g. ConvoScribe on port 8020).

## Quick start (Docker)

```bash
cd ORScribe
cp .env.example .env
docker compose up --build
```

API: http://localhost:8030  
Docs: http://localhost:8030/docs  
Health: http://localhost:8030/api/v1/health  
MinIO console: http://localhost:9003

## Local development

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export DATABASE_URL=postgresql://orscribe:orscribe@localhost:5434/orscribe
export USE_LLM_STUB=true
export TRANSCRIPTION_BACKEND=stub

python main.py
# or: uvicorn main:app --reload --port 8030

# In another terminal:
celery -A app.jobs.celery_app.celery_app worker --loglevel=info
```

## Run a sample case

No request headers are required.

```bash
curl -X POST http://localhost:8030/api/v1/analyze \
  -F "audio=@samples/or_case_sample.wav"

curl -X POST http://localhost:8030/api/v1/cases \
  -F "procedure_type=laparoscopic cholecystectomy" \
  -F "ingest_mode=post_hoc" \
  -F "audio=@sample.wav"
```

Poll `GET /api/v1/cases/{id}` until `status` is `completed`.

Per-window transcription (used by ORVoiceAgent; does not run role/timeline/checklist):

```bash
curl -X POST http://localhost:8030/api/v1/windows/transcribe \
  -F "audio=@samples/or_case_sample.wav" \
  -F "case_id=case-123" \
  -F "window_id=nursing_time_out" \
  -F "role=nurse"
```

Valid `window_id` values: `nursing_verification_of_marking_site`, `nursing_time_out`, `nursing_intraoperative`, `nursing_sign_out`, `anesthesia_pre_evaluation_plan`, `anesthesia_induction_intraoperative`, `anesthesia_observation_drugs`, `operative_note`.
Valid `role` values: `nurse`, `anesthetist`, `surgeon`.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/analyze` | One-shot — upload audio, get transcript + roles + timeline + checklist |
| POST | `/api/v1/windows/transcribe` | Per-window STT — audio in, single text block out (no roles/timeline) |
| POST | `/api/v1/cases` | Start a case (metadata + optional audio) |
| POST | `/api/v1/cases/{id}/audio-chunk` | Push audio chunk for streaming cases |
| GET | `/api/v1/cases/{id}` | Full case record |
| GET | `/api/v1/cases/{id}/transcript` | Raw diarized transcript |
| PATCH | `/api/v1/cases/{id}/roles` | Human role correction |
| GET | `/api/v1/cases/{id}/checklist` | Checklist verification result |
| POST | `/api/v1/cases/{id}/approve` | Clinical staff sign-off |
| GET | `/api/v1/health` | Service health |

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_PORT` | `8030` | Server port |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ROLE_ID_MODEL` | `gpt-4o` | Role identification model |
| `RECORD_MODEL` | `gpt-4o` | Timeline + checklist model |
| `USE_LLM_STUB` | `false` | Offline rule-based LLM for dev/CI |
| `TRANSCRIPTION_BACKEND` | `stub` | `stub` or `whisper_pyannote` |
| `AUDIO_RETENTION_DAYS` | `30` | Auto-delete raw audio after N days |

See `.env.example` for the full list.

## Testing

```bash
pytest
```

## Postman

Import `postman/ORScribe.postman_collection.json` into Postman.

Set collection variables:
- `baseUrl` — `http://localhost:8030`
- `apiKey` — your API key from `.env`
- `staffId` — e.g. `nurse-1`

Creating a case auto-saves `caseId` for subsequent requests. For file upload requests, select an audio file in the **audio** form field.

## Project structure

```
ORScribe/
├── main.py              # FastAPI entry point
├── postman/             # Postman collection
├── app/
│   ├── api/routes.py    # /api/v1 endpoints
│   ├── ai/              # OpenAI client, prompts, domain logic
│   ├── core/            # Config, auth, logging
│   ├── db/              # SQLAlchemy models
│   ├── jobs/            # Celery tasks
│   ├── models/          # Pydantic schemas
│   ├── services/        # Business logic (including window_transcribe_service)
│   ├── storage/         # S3 object storage
│   └── transcription/   # Pluggable transcription backends
└── tests/
```
