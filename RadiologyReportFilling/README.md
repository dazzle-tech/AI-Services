# Medical Imaging Assist

A FastAPI service that assists radiologists by validating DICOM metadata,
correcting reporting errors, and reconciling AI image analysis with clinical
documentation. **All output is assistive only and requires board-certified
radiologist review.**

## What it does

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/report-correction` | Compatibility route for the workflow. Uses `radiologist_notes` as the base report, flags obvious contradictions against `doctor_notes`, and returns `clinical_report_text`. |
| `POST /api/v1/analysis-matching` | Compatibility route for the workflow. Compares AI findings against the clinical report, returns `reconciled_findings`, and suggests ICD-10 codes from local RAG data. |
| `POST /api/v1/report-filling` | Existing template-generation endpoint driven by patient/order/DICOM metadata. |
| `GET /api/v1/health` | Liveness / config check. |
| `GET /api/v1/terms/summary` | Loaded ICD-10 and RadLex counts (no AI call). |

`report-correction` and `analysis-matching` both return a deterministic compatibility response that includes
top-level workflow fields plus a nested `safety_normalized_output` object.

`report-filling` returns the newer template-only contract documented elsewhere in this README.

## Setup

### 1. Clone and create a virtual environment

```powershell
cd "C:\Users\jirie\Documents\Image Analysis"
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy the template and review the AI settings:

```powershell
copy .env.example .env
notepad .env
```

Default local Ollama configuration in `.env`:

```
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL=qwen3:1.7b
OPENAI_EMBED_MODEL=nomic-embed-text
```

`qwen3:1.7b` is suitable for Report Filling because this endpoint is a
text-generation task. It is not suitable for image interpretation.

Local Ollama setup:

```bash
ollama pull qwen3:1.7b
ollama run qwen3:1.7b
```

To switch back to the OpenAI cloud API, set `OPENAI_BASE_URL=` and replace
`OPENAI_API_KEY` with a real key.

> The `.env` file is gitignored. Never commit it.

### 3. (Optional) Build the RAG embeddings cache

The service works out of the box with **keyword-fallback** retrieval against
`rag_data/icd10cm.json` and `rag_data/radlex.json`. To enable semantic
retrieval, run the one-time ingestion:

```powershell
python -m app.services.rag_store ingest
```

This calls the configured OpenAI-compatible embeddings API once and writes
`rag_data/embeddings.npz`.
The file is gitignored.

### 4. Run the server

```powershell
python main.py
```

The server starts on `http://localhost:8024`.

- Swagger UI: `http://localhost:8024/docs`
- ReDoc: `http://localhost:8024/redoc`

### 5. Run the tests

```powershell
pytest tests/ -v
```

Tests mock the chat-completions API call, so they do not require a working
remote key. The RAG embeddings cache still needs to be regenerated separately if
you want semantic retrieval with the local `nomic-embed-text` model.

## Using the API in Postman

### Postman request table

| Method | URL | Headers | Body |
|---|---|---|---|
| `GET` | `http://localhost:8024/` | -- | -- |
| `GET` | `http://localhost:8024/api/v1/health` | -- | -- |
| `GET` | `http://localhost:8024/api/v1/terms/summary` | -- | -- |
| `POST` | `http://localhost:8024/api/v1/report-correction` | `Content-Type: application/json` | see body below |
| `POST` | `http://localhost:8024/api/v1/analysis-matching` | `Content-Type: application/json` | see body below |
| `POST` | `http://localhost:8024/api/v1/report-filling` | `Content-Type: application/json` | static-template, compact-workflow, or debug full-workflow payload |

### Postman collection requests

The bundled collection file `Medical_Imaging_Assist.postman_collection.json`
uses the `{{base_url}}` variable and now includes three report-filling request
variants:

- `Report Filling - Static Template Test`: fast smoke test with metadata-only
  input. It can return a valid template response without necessarily exercising
  the AI report-generation path.
- `Report Filling - Compact Workflow Payload`: mirrors the production Stage 3
  workflow body by sending patient/order fields plus compact
  `AIInterpretationSummary`, `QC`, and minimal `DICOM` metadata. This is the
  preferred request for real workflow testing because it exercises the AI
  report-generation path without flooding the prompt with large debug objects.
- `Report Filling - Full Workflow Payload (Debug)`: retains the older large
  body with full `AIInterpretation`, `QCResult`, and `DICOM` objects for
  troubleshooting only.

### Why the workflow payload is compact

Report Filling should receive report-generation context, not the full
workflow/debug payload. Full DICOM metadata belongs to the QC and
Interpretation services, which need the detailed study data. Report Filling
only needs minimal exam metadata plus short workflow summaries so the prompt
stays small enough for local models such as `qwen3:1.7b`.

If the configured text model returns invalid JSON, times out, or fails for any
other reason, Report Filling now returns HTTP `200` with a valid report object
built from `RadiologistNotes` instead of breaking the workflow with `422`.

`RadiologistNotes` are always treated as the primary source of truth for final
report content. `DoctorNotes` are used only as supporting clinical context.

The recommended compact payload keeps:

- patient and order identifiers
- doctor notes as secondary clinical context
- radiologist notes as the primary source for final report content
- a short AI interpretation summary for warning/context only
- a short QC summary for warning/context only
- minimal DICOM metadata for modality, body part, study date, view, and study ID

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

### Greek output (`output_language: "el"`)

Set `output_language` to `"el"` (or `"en"` for English) to control the language of user-facing
fields (`corrected_*_notes`, `structured_report`, `findings`, `warnings.message`, and matching
reconciliation text). JSON keys, ICD-10 codes, RadLex IDs, DICOM tags, and warning `code` values
stay in English.

```json
{
  "doctor_notes": "Ο ασθενής παραπέμπεται για ακτινογραφία θώρακος.",
  "radiologist_notes": "Χωρίς ενεργό νόσο από το πνευμονικό παρέγχυμα, με ορατές τις πλευροδιαφραγματικές γωνίες. ΚΘΔ ΚΦ. Μεσοθωράκιο, μαλακά μόρια, οστά χωρίς ιδιαίτερα ευρήματα. Μόλις υποσημαινόμενη επίταση βρογχοαγγειακού δικτύου παρατηρείται άμφω. Αποτιτάνωση Αορτής. Ελίκωση Αορτής.",
  "exam_type": "Ακτινογραφία θώρακος",
  "output_language": "el",
  "extracted_dicom_metadata": {
    "Modality": "DX",
    "BodyPartExamined": "CHEST",
    "ViewPosition": "PA"
  }
}
```

Expected behavior:
- `structured_report`, `findings.label` / `location`, and corrected notes are in Greek.
- `warnings[].code` (e.g. `SPELLING_CORRECTED`) and DICOM values such as `CHEST` remain unchanged.
- Omit `output_language` to keep the default English prompt behavior.

Expected behavior (English example):
- `clinical_report_text` uses `radiologist_notes` as the base report text.
- `warnings` contains `LATERALITY_CONFLICT` when the doctor and radiologist notes disagree on left vs right.
- `safety_normalized_output.rag_grounding.icd10_codes` contains local ICD-10 suggestions based on the report text.

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

For Greek reconciliation output, add `"output_language": "el"` to the same request shape.

Expected behavior:
- `reconciled_findings` marks each AI item as `matched`, `partial`, or `unmatched` against the clinical report text.
- Findings negated by the report text are returned as `unmatched`.
- `suggested_icd10_codes` contains local ICD-10 candidates based on the report and matched findings.

### Loading sample bodies from disk

Six pre-built request bodies (one per test case in `xray_test_examples.json`) live in
`sample_requests/`. In Postman, click the **Body** tab -> **raw** -> the
**file icon** (top-right) to load one of these JSON files directly. The
filenames are self-describing:

- `correction_TC_001_Laterality_Conflict.json`
- `correction_TC_002_Shorthand_ICD10.json`
- `correction_TC_003_Misspelling_Formatting.json`
- `correction_DX_CHEST_T3_Greek_Output.json` (Greek CXR, `output_language: "el"`)
- `matching_TC_004_Hierarchy_Of_Truth.json`
- `matching_TC_005_AI_Enrichment.json`
- `matching_TC_006_Metadata_Mismatch.json`

Regenerate them anytime with `python generate_data.py`.

### Swagger UI alternative

Open `http://localhost:8024/docs` for interactive testing without Postman.

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

## CI workflow (.github/workflows/radiology-report-filling-ci.yml)

## Disclaimer

This service is for assistive purposes only and is not a final diagnosis.
All output requires review by a board-certified radiologist.
