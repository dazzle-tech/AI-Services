# Radiology AI Pipeline (n8n)

This folder contains:

- `radiology_n8n_workflow.json` - main pipeline workflow
- `radiology_n8n_error_workflow.json` - error-trigger alert workflow (import separately)
- `main.py` - local launcher API + simple web UI
- `index.html` - the UI page

## Import (n8n)

1. Open n8n (usually `http://localhost:5678`)
2. Workflows -> **Import from File**
3. Import `radiology_n8n_workflow.json`
4. Import `radiology_n8n_error_workflow.json`

## Important

- The pipeline HTTP nodes expect the DICOM ZIP as incoming **binary** data in `binary.data`.
  - For local testing from a path, insert a **Read/Write Files from Disk (Read)** node before "Stage 1 — Image QA" to load `dicom_file_path` into binary field `data`, then connect it forward.
- On Windows, `localhost` may resolve to IPv6 (`::1`). If your services only listen on IPv4, change URLs from `http://localhost:...` to `http://127.0.0.1:...` in the workflow.
- If n8n runs in Docker, change `localhost` to `host.docker.internal`.

## Quick health check

Run `check_services.ps1` to verify each service health endpoint over IPv4 (`127.0.0.1`).

## Simple UI (recommended for quick testing)

1. Start: `python main.py` (or `py main.py` on Windows)
2. Open: `http://127.0.0.1:8090`
3. Services auto-start on launch. Upload a DICOM `.dcm` (single image) or `.zip` and click "Run".
   - The UI streams progress and updates each stage as soon as it finishes.
4. After review, click "Approve & Save draft" to write the full run output JSON into `saved/`.
5. If QA returns `REVIEW_REQUIRED`, click "Approve QA & Continue" to proceed with a manual override.

## DICOM auto-fill

- On file select, the UI calls `POST /api/parse-dicom` to auto-fill patient/study fields from the DICOM header.
- `pydicom` is required for this feature; see `requirements.txt`.
