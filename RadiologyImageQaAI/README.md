# Radiology QC AI (MVP)

Radiology QC AI is a **research/production-style MVP backend** for **technical image quality control** in hospital radiology workflows.

Initial focus: **CT Abdomen/Pelvis anatomical coverage QC**
- Verify **superior** coverage includes **diaphragm / lung bases**
- Verify **inferior** coverage includes **lower pelvis / pubic symphysis**
- Returns `PASS` / `WARNING` / `FAIL` plus a human-readable explanation

## Safety / regulatory disclaimer (required)
**Research/MVP only. Not for clinical use without validation and regulatory approval.**

This service:
- Checks **technical coverage only**
- Does **not** diagnose, detect disease, or provide clinical interpretation

## How coverage is checked
Preferred open-source model: **TotalSegmentator** (Apache 2.0). Preserve license notices when redistributing.  
In this MVP:
- TotalSegmentator is used (when available) to generate segmentation masks
- Landmark detection uses **simple heuristics** (mask existence and proxies)
- Rules in `app/qc_rules.py` determine `PASS/WARNING/FAIL`

**Important:** The heuristic landmark logic is not validated and is not suitable for clinical use.

## Repository layout
```
radiology-qc-ai/
  app/                       # FastAPI service
  tests/                     # pytest tests
  postman/                   # Postman collection + environment
  sample_data/               # no PHI included
  main.py                    # service entrypoint (repo standard)
  Dockerfile
  docker-compose.yml
  requirements.txt
  pytest.ini
  .dockerignore
  .env                       # local defaults (gitignored)
  .env.example
  README.md
```

## Quick start (local)
Prereqs: Python 3.11+

```powershell
cd radiology-qc-ai
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8016
```

Open: `http://localhost:8016/api/v1/health` (or `http://localhost:8016/health`)

## Quick start (Docker)
```powershell
cd radiology-qc-ai
docker compose up --build
```

## API overview

### 1) Health check
`GET /health`

### 2) Upload a CT DICOM study (zip or single .dcm) (CT QC)
`POST /api/v1/qc/ct/dicom` (multipart form-data)
- `file`: zip containing DICOM series, or a single `.dcm` file
- `use_gpt_report`: boolean (default `false`)

Behavior:
- Extracts zip to a temp folder
- Reads metadata with `pydicom`
- Classifies protocol from Study/Series/Protocol fields
- If CT: converts to NIfTI (`dicom2nifti`) and attempts segmentation (TotalSegmentator)
- If TotalSegmentator is missing/fails: returns `qc_status=REVIEW_REQUIRED` (graceful)

### 3) Upload an X-ray DICOM study (zip or single .dcm) (X-ray intake)
`POST /api/v1/qc/xray/dicom` (multipart form-data)
- `file`: zip containing DICOM series, or a single `.dcm` file

Behavior:
- Extracts zip to a temp folder
- Reads metadata with `pydicom`
- Tracks as `exam_type=XRAY` and returns `REVIEW_REQUIRED` (no automated X-ray QC in this MVP)

### 4) Generate an explanation from structured QC JSON
`POST /api/v1/report/explain`

## Medical Image Interpretation Assist Service

Purpose:
- Identify suspected candidate findings from medical images as structured JSON.
- Assistive interpretation support only; not final diagnosis and not report generation.

Inputs:
- Zipped DICOM study (`/api/v1/radiology/interpretation/dicom`)
- DICOM metadata
- Optional clinical indication
- Optional segmentation-derived mask signals (when available)

Outputs:
- Structured suspected findings JSON with:
  - `findings` list of AI-detected candidate findings
  - `critical_alert` flag if any candidate is marked `CRITICAL`
  - explicit assistive disclaimer and radiologist-review requirement

Safety limitations:
- This service does not confirm diagnosis.
- Wording is intentionally uncertain (possible/suspected/candidate finding).
- No report drafting, template filling, correction, or final report generation.
- Production diagnostic interpretation requires validated disease-specific models.

Difference from Image Quality Check:
- QC service checks technical scan coverage quality.
- Interpretation Assist service proposes possible image findings for radiologist review.

Human-in-the-loop workflow:
- PACS/DICOM router sends study -> service returns candidate findings -> radiologist reviews and confirms/rejects.

Regulatory warning:
- Assistive AI only. Radiologist review required. Not for final diagnosis.

How to test with Postman:
- Import `postman/Medical_Image_Interpretation_Assist.postman_collection.json`
- Run:
  - Health
  - DICOM Interpretation Upload

## OpenAI (optional, text-only)
OpenAI is **optional** and used only to **phrase** the explanation text.

Defaults:
- `OPENAI_ENABLED=false`
- `DEIDENTIFY_BEFORE_GPT=true`

Do not send PHI by default. The service only sends a minimal structured QC summary when de-identification is enabled.

## Testing
```powershell
cd radiology-qc-ai
pytest -q
```

## Postman
Import:
- `postman/Radiology_QC_AI.postman_collection.json`
- `postman/Radiology_QC_AI.postman_environment.json`

Requests included:
- Health
- Explanation generation
- CT DICOM zip upload (you provide your own `sample.zip`)
- X-ray DICOM zip upload (you provide your own `sample.zip`)

## Hospital integration overview (high-level)
Typical flow:
Scanner/PACS/DICOM router → **Radiology QC AI** → QC result → technologist dashboard / RIS / PACS note

Recommended integration approach:
- Run in **silent mode** first (no workflow interruption)
- Log QC results + human outcomes
- Tune thresholds and validate per protocol/site

## Recommended production path
1. Offline validation on de-identified datasets
2. Retrospective study against site protocols
3. Silent mode pilot (monitoring only)
4. Human-in-the-loop clinical pilot
5. Regulatory review and quality management system alignment
