# OCR Parsing Service

FastAPI service that combines:
- OCR extraction from image files with the OpenAI vision model (`OPENAI_MODEL`, default `gpt-4o`)
- Structured parsing of extracted text using the same model

## Endpoints

- `POST /api/v1/extract-text`
  - Input: image file (multipart form-data, field name: `file`)
  - Output: extracted `text_lines`

- `POST /api/v1/parse-text`
  - Input JSON:
    ```json
    {
      "text_lines": ["line 1", "line 2"]
    }
    ```
    or
    ```json
    {
      "text": "full raw text"
    }
    ```
  - Output: parsed JSON object

- `POST /api/v1/extract-and-parse`
  - Input: image file
  - Output: OCR `text_lines`, parsed `structured_data`, and the model name

- `GET /api/v1/health`
  - Basic health check

- `POST /api/v1/identity/extract`
  - Input: image file (multipart form-data, field name: `file`), optional `strict_quality` (default `true`)
  - Output: identity fields, OCR quality, validation, and the recognized text lines

## Data handling

The uploaded image is rotated upright, converted to pixels, and re-encoded as a JPEG with no EXIF or GPS. The longest side is limited to 2048 pixels. That JPEG is sent to the configured OpenAI endpoint (`OPENAI_BASE_URL`, default `https://api.openai.com/v1`) using `OPENAI_VISION_MODEL` when set, otherwise `OPENAI_MODEL`. Point `OPENAI_BASE_URL` at a regional or Azure OpenAI endpoint to keep the request on that host. The service does not log or store the image, the base64 payload, or the recognized text lines.

```json
{
  "identity": {
    "full_name": "Jane Doe",
    "date_of_birth": "1990-03-02",
    "gender": "female",
    "nationality": "CAN",
    "document_number": "AB123456",
    "document_type": "unknown",
    "extraction_source": "visual"
  },
  "quality": {
    "avg_confidence": 0.92,
    "min_confidence": 0.9,
    "low_confidence_fraction": 0.0,
    "image_width_px": 800,
    "image_height_px": 700,
    "image_rotation_degrees": 0,
    "blur_variance": 120.0,
    "brightness_mean": 100.0,
    "contrast_std": 40.0,
    "is_low_quality": false,
    "warnings": []
  },
  "validation": { "ok": true, "errors": [], "warnings": [] },
  "mrz_present": false,
  "mrz_valid": null,
  "text_lines": [
    "Name: JANE DOE",
    "Date of Birth: 02/03/1990",
    "Sex: F",
    "Nationality: CAN",
    "Passport No: AB123456"
  ]
}
```

## Run locally

1. (Recommended) Create and activate a virtual environment
   - `py -m venv .venv`
   - `./.venv/Scripts/Activate.ps1`
2. Install dependencies
   - `py -m pip install -r requirements.txt`
3. Copy `.env.example` to `.env`
4. Set `OPENAI_API_KEY` in `.env`
5. Start service:
   - `uvicorn main:app --host 0.0.0.0 --port 8012 --reload`

## Run with Docker

1. Copy `.env.example` to `.env`
2. `docker compose up -d --build`

Service runs on port `8012`.

## Postman

Import [`postman/OCRParsingService.postman_collection.json`](postman/OCRParsingService.postman_collection.json).
Set collection variable `baseUrl` (default `http://localhost:8012`).

The unified repo collection at [`../postman_collection.json`](../postman_collection.json) includes an **OCRParsingService** folder using `ocrparsingservice_base_url`.

## CI workflow (.github/workflows/ocr-parsing-ci.yml)
