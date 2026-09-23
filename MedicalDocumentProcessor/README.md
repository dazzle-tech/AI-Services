# Medical Document Processor Service

AI-powered intake pipeline for uploaded medical documents, using OpenAI GPT. Accepts a
document of any common format, validates it against the given patient's identity,
checks whether it's still clinically relevant, translates it if needed, and returns a
structured, document-type-specific extraction.

**Important:** This service performs intake support only -- it does not diagnose and does
not replace clinical review of the uploaded document.

## Overview

- **Purpose:** Turn an arbitrary uploaded medical document into validated, relevant,
  optionally-translated, structured JSON -- or a clear reason why it was rejected.
- **Architecture:** Layered design (API -> Orchestrator -> 4 pipeline-step services ->
  AI Client -> Prompts), consistent with LabResultInterpreterService / OCRParsingService.
  Structured formatting uses a formatter registry (strategy pattern) keyed by document
  type, so new document types can be added without touching the pipeline logic.
- **Pipeline:**
  1. **Validation** -- extract text, cross-check patient-identifying signals in the
     document against the given patient record. Stops here on a clear mismatch.
  2. **Relevance** -- classify against configurable per-document-type recency windows
     (and, optionally, existing documents already on record). Stops here if outdated
     or superseded.
  3. **Translation** -- always detects the document's language; translates only if
     `translate=true` and the detected language differs from `target_language`.
  4. **Structured formatting** -- classifies the document type and shapes the
     (possibly translated) text into a type-specific structured schema.
- **Output:** A single response object regardless of where the pipeline stopped:
  `status`, `reason`, `detected_language`, `translated`, `document_type`,
  `structured_data`, `raw_extracted_text` (always present, for traceability).

## Supported input formats

| Format    | Extraction method                                                      |
|-----------|--------------------------------------------------------------------------|
| PDF       | `pypdf` (text-based PDFs only; scanned/image-only PDFs are rejected as INVALID in this version -- see Known limitations) |
| DOCX      | `python-docx`                                                            |
| TXT       | plain decode                                                             |
| CSV       | stdlib `csv`                                                             |
| JPG / PNG | OCR via `gpt-4o` vision (default) or local `easyocr` (optional, `OCR_ENGINE=easyocr`) |

## Quick Start

### Run Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env and add your OpenAI API key

# 3. Run the server
python main.py

# 4. Test the API
curl http://localhost:8029/api/v1/health
```

### Run with Docker

```bash
docker-compose up --build
```

## Configuration

| Variable                       | Description                                            | Default    |
|---------------------------------|----------------------------------------------------------|------------|
| `OPENAI_API_KEY`                | OpenAI API key (required)                                | -          |
| `OPENAI_MODEL`                  | Model used for all 4 text pipeline steps                 | `gpt-4o`   |
| `OPENAI_VISION_MODEL`           | Model for image OCR; falls back to `OPENAI_MODEL`        | -          |
| `OPENAI_TEMPERATURE`            | Temperature                                               | `0.1`      |
| `MAX_INPUT_LENGTH`              | Extracted text is truncated to this many chars in prompts | `60000`    |
| `MAX_UPLOAD_SIZE_MB`            | Max accepted upload size                                  | `20`       |
| `DEFAULT_TARGET_LANGUAGE`       | Used when `target_language` isn't supplied                | `en`       |
| `OCR_ENGINE`                    | `vision` (gpt-4o) or `easyocr` (local, optional dep)       | `vision`   |
| `RELEVANCE_WINDOWS_DAYS_JSON`   | Per-document-type max age (days), see Step 2              | see `.env.example` |
| `API_PORT`                      | Server port                                                | `8029`     |
| `LOG_LEVEL`                     | Logging level                                              | `INFO`     |

## API Endpoints

### `POST /api/v1/process-document`

`multipart/form-data`:

| Field                | Type   | Required | Notes                                                       |
|----------------------|--------|----------|--------------------------------------------------------------|
| `file`               | file   | yes      | PDF, DOCX, TXT, CSV, or JPG/PNG                               |
| `patient`            | string | yes      | JSON-encoded `{patient_id, full_name, sex, date_of_birth}`   |
| `translate`          | bool   | no       | Default `false`                                               |
| `target_language`    | string | no       | Defaults to `DEFAULT_TARGET_LANGUAGE`                         |
| `existing_documents` | string | no       | JSON array of `{document_type, document_date}` for supersede checks in Step 2 |

**Example (`curl`):**

```bash
curl -X POST http://localhost:8029/api/v1/process-document \
  -F "file=@lab_report.pdf" \
  -F 'patient={"patient_id":"P-1001","full_name":"Jane Doe","sex":"female","date_of_birth":"1980-05-14"}' \
  -F "translate=true" \
  -F "target_language=en"
```

**Example response (processed):**

```json
{
  "status": "processed",
  "reason": null,
  "detected_language": "fr",
  "translated": true,
  "document_type": "lab_result",
  "structured_data": {
    "document_type": "lab_result",
    "test_date": "2026-08-01",
    "ordering_provider": "Dr. Amina Hassan",
    "results": [
      {"test_name": "WBC", "value": "11.2", "unit": "10^9/L", "reference_range": "4.0-11.0", "flag": "high"}
    ]
  },
  "raw_extracted_text": "...",
  "request_id": "req_20260823_090000",
  "processing_metadata": {"stage": "completed", "model": "gpt-4o", "target_language": "en"}
}
```

**Example response (invalid patient match):**

```json
{
  "status": "invalid",
  "reason": "Document indicates sex 'male' but patient record states 'female'",
  "detected_language": null,
  "translated": false,
  "document_type": null,
  "structured_data": null,
  "raw_extracted_text": "..."
}
```

**Example response (irrelevant / outdated):**

```json
{
  "status": "irrelevant",
  "reason": "Blood test dated 2019-03-11 -- outside the 180-day relevance window for lab_result.",
  "detected_language": null,
  "translated": false,
  "document_type": null,
  "structured_data": null,
  "raw_extracted_text": "..."
}
```

### `GET /api/v1/health`

Health check and OpenAI configuration status.

## Postman Collection

Import `postman/MedicalDocumentProcessor.postman_collection.json`, set `baseUrl` to
`http://localhost:8029`, and run: Health Check, Process Document (valid, no translation),
Process Document (valid, translation required), Process Document (invalid patient match),
Process Document (irrelevant/outdated).

## Testing

```bash
pytest                    # all tests
pytest tests/unit/        # unit tests only (per pipeline step)
pytest tests/integration/ # integration tests (full pipeline via the API)
```

Integration tests cover: (a) invalid patient match, (b) irrelevant/outdated document,
(c) valid document requiring translation, (d) valid document not requiring translation.

## Extensibility

- **New document types:** add a structured schema in `app/models/schemas.py`, a
  formatter in `app/services/formatters/`, and register it in
  `app/services/formatters/__init__.py`. No changes needed to the pipeline orchestration.
- **Relevance thresholds:** tune `RELEVANCE_WINDOWS_DAYS_JSON` per document type without
  a code change.
- **New file formats:** add an extractor module under `app/extraction/` and wire it into
  `file_extractor.py`'s format dispatch.

## Known limitations (v1)

- Scanned/image-only PDFs (no extractable text layer) are rejected as `invalid` rather
  than OCR'd -- only JPG/PNG scans go through the OCR path. Re-scan or re-export such
  PDFs as an image to process them.
- The relevance check (Step 2) independently infers the document's apparent type and
  date rather than depending on Step 4's formal classification (which hasn't run yet in
  pipeline order) -- keeping each step self-contained and independently testable. Step 4
  performs the authoritative classification used in the final output.

## Safety

- **Intake support only:** does not diagnose. Patient-match and relevance decisions are
  deterministic where possible (guardrails on top of the LLM's own judgment), and every
  rejection includes a specific reason.
- **Traceability:** `raw_extracted_text` is always included in the response, regardless
  of pipeline outcome.

## Disclaimer

This is an AI-powered intake support tool. All output should be reviewed by qualified
healthcare professionals. AI systems can make errors -- always verify accuracy before
clinical use.
