# Medical Imaging Assist

A FastAPI service that assists radiologists by validating DICOM metadata,
correcting reporting errors, and reconciling AI image analysis with clinical
documentation. **All output is assistive only and requires board-certified
radiologist review.**

## What it does

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/report-correction` | Fixes misspellings, expands shorthand, cross-checks doctor vs. radiologist notes for laterality conflicts, grounds findings in ICD-10 / RadLex. |
| `POST /api/v1/analysis-matching` | Reconciles a finalized clinical report (authoritative) with an AI image analysis result. Drops AI findings that contradict the report; uses non-conflicting AI detail to enrich. |
| `GET /api/v1/health` | Liveness / config check. |
| `GET /api/v1/terms/summary` | Loaded ICD-10 and RadLex counts (no AI call). |

The response envelope follows a **sibling architecture**:
- `raw_model_output` -- untouched GPT-4o JSON for auditability.
- `safety_normalized_output` -- deterministic-rule-corrected output for clinicians.
- `disclaimer` -- standard assistive-AI text.

## Setup

### 1. Clone and create a virtual environment

```powershell
cd "C:\Users\jirie\Documents\Image Analysis"
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy the template and add your OpenAI key:

```powershell
copy .env.example .env
notepad .env    # paste your OPENAI_API_KEY
```

Required key in `.env`:

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

> The `.env` file is gitignored. Never commit it.

### 3. (Optional) Build the RAG embeddings cache

The service works out of the box with **keyword-fallback** retrieval against
`rag_data/icd10cm.json` and `rag_data/radlex.json`. To enable semantic
retrieval, run the one-time ingestion:

```powershell
python -m app.services.rag_store ingest
```

This calls the OpenAI Embeddings API once and writes `rag_data/embeddings.npz`.
The file is gitignored.

### 4. Run the server

```powershell
python main.py
```

The server starts on `http://localhost:8000`.

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 5. Run the tests

```powershell
pytest tests/ -v
```

Tests mock the OpenAI API call, so they do not require a working key.

## Using the API in Postman

### Postman request table

| Method | URL | Headers | Body |
|---|---|---|---|
| `GET` | `http://localhost:8000/` | -- | -- |
| `GET` | `http://localhost:8000/api/v1/health` | -- | -- |
| `GET` | `http://localhost:8000/api/v1/terms/summary` | -- | -- |
| `POST` | `http://localhost:8000/api/v1/report-correction` | `Content-Type: application/json` | see body below |
| `POST` | `http://localhost:8000/api/v1/analysis-matching` | `Content-Type: application/json` | see body below |

### Setting up a POST request

1. Set the method to **POST** and enter the URL.
2. Go to the **Headers** tab and add `Content-Type: application/json`.
3. Go to the **Body** tab, choose **raw**, and set the format dropdown to **JSON**.
4. Paste one of the bodies below (or load a file from `sample_requests/`).
5. Click **Send**.

### Example body for `/api/v1/report-correction`

```json
{
  "doctor_notes": "Patient presenting with acute chest pain and persistent cough. Suspected left-sided pneumonia.",
  "radiologist_notes": "PA/Lateral Chest: Consolidation and opacity noted in the right lower lobe. No evidence of pneumothorax.",
  "exam_type": "Chest X-ray 2 Views",
  "extracted_dicom_metadata": {
    "PatientID": "12345",
    "Modality": "CR",
    "BodyPartExamined": "CHEST",
    "ViewPosition": "PA",
    "StudyDate": "20260513"
  }
}
```

Expected behavior:
- `safety_normalized_output.warnings` contains `LATERALITY_CONFLICT` (severity `high`).
- `safety_normalized_output.confidence` is `Low`.
- `safety_normalized_output.rag_grounding.icd10_codes` contains `J18.9`.

### Example body for `/api/v1/analysis-matching`

```json
{
  "clinical_report": "Follow-up of pulmonary nodule. A stable 1.2cm nodule is noted in the left upper lobe.",
  "ai_image_analysis": {
    "findings": [
      {
        "label": "Nodule",
        "location": "Left Upper Lobe",
        "size_mm": 18,
        "confidence": 0.92
      }
    ]
  },
  "extracted_dicom_metadata": {
    "Modality": "DX",
    "ViewPosition": "PA",
    "StudyDescription": "CHEST SINGLE VIEW"
  }
}
```

Expected behavior:
- `safety_normalized_output.findings` keeps the doctor's `1.2cm` size, NOT the AI's `1.8cm`.
- `safety_normalized_output.reconciled_findings[0].ai_variance` records the AI delta.
- `safety_normalized_output.warnings` contains `AI_SIZE_VARIANCE` (severity `high`).

### Loading sample bodies from disk

Six pre-built request bodies (one per test case in `xray_test_examples.json`) live in
`sample_requests/`. In Postman, click the **Body** tab -> **raw** -> the
**file icon** (top-right) to load one of these JSON files directly. The
filenames are self-describing:

- `correction_TC_001_Laterality_Conflict.json`
- `correction_TC_002_Shorthand_ICD10.json`
- `correction_TC_003_Misspelling_Formatting.json`
- `matching_TC_004_Hierarchy_Of_Truth.json`
- `matching_TC_005_AI_Enrichment.json`
- `matching_TC_006_Metadata_Mismatch.json`

Regenerate them anytime with `python generate_data.py`.

### Swagger UI alternative

Open `http://localhost:8000/docs` for interactive testing without Postman.

## Project layout

```
Image Analysis/
  main.py                          FastAPI entry point
  .env / .env.example              Config (.env is gitignored)
  output_schema.json               Response envelope JSON Schema
  medical_terms_guide.txt          Domain rules for the AI prompt
  generate_data.py                 Builds sample_requests/ from xray_test_examples.json
  xray_test_examples.json          Source test cases
  Dockerfile / docker-compose.yml / deploy.sh
  requirements.txt
  rag_data/
    icd10cm.json                   ICD-10-CM term set
    radlex.json                    RadLex term set
    embeddings.npz                 (created by ingest; gitignored)
  app/
    core/config.py                 Pydantic Settings
    ai/client.py                   OpenAI client + retry logic
    ai/prompts.py                  System / user prompt builders
    models/schemas.py              Request / response Pydantic models
    services/medical_service.py    Orchestration (load -> retrieve -> prompt -> AI -> normalize -> save)
    services/safety_normalizer.py  Deterministic sibling-output rules
    services/rag_store.py          Local ICD-10 / RadLex retrieval
    api/routes.py                  FastAPI router
  tests/test_routes.py             Mocked endpoint tests (TC_001, TC_004 + health/summary/validation)
  sample_requests/                 Postman-ready JSON bodies
  output/                          (created at runtime; gitignored; PHI-bearing)
```

## Docker

```bash
./deploy.sh build      # build image and start container
./deploy.sh logs       # tail logs
./deploy.sh restart    # rebuild and restart
./deploy.sh stop       # stop the container
```

The container reads `.env` and mounts `./output` for persisted responses.

## Output persistence

Every successful AI call is persisted to `./output/<endpoint>_<utc_timestamp>.json`.
These files contain PHI; the directory is gitignored. To disable persistence,
set `PERSIST_OUTPUT=false` in `.env`.

## Disclaimer

This service is for assistive purposes only and is not a final diagnosis.
All output requires review by a board-certified radiologist.
