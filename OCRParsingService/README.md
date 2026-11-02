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
  - Output: OCR lines + parsed structured data

- `GET /api/v1/health`
  - Basic health check

- `POST /api/v1/identity/extract`
  - Input: image file (multipart form-data, field name: `file`), optional `strict_quality` (default `true`)
  - Output: identity fields, OCR quality, validation, and the position data below

## Positions and field sources

`POST /api/v1/identity/extract` adds `lines`, `field_sources`, and `image` on top of the existing identity payload. Older clients can ignore them.

Coordinates are normalized from 0 to 1, origin at the top-left, relative to the upright image after EXIF orientation is applied. The vision model returns each box. Phone photos are rotated to the same upright view the browser shows before any box is measured. `image.original_width_px` and `image.original_height_px` are that upright size. `quality.image_width_px` and `quality.image_height_px` are the same upright size. Confidence values are reported by the vision model.

To draw a box over the upright image:

- `left = x * 100%`
- `top = y * 100%`
- `width = w * 100%`
- `height = h * 100%`

`lines` is in the same order as `text_lines`. `lines[i].text` is `text_lines[i]`, and `lines[i].box` is the detected chunk. A box can include the printed label on that chunk, not only the value.

`field_sources` maps `full_name`, `date_of_birth`, `gender`, `nationality`, and `document_number` to:

- `line_indices`: indexes into `lines` / `text_lines`
- `source_kind`: `visual` (printed labels), `mrz` (the MRZ block; every MRZ line that was parsed), or `llm`
- `confidence`: the lowest model-reported confidence among those lines, when known
- `level`: `high` (>= 0.90), `medium` (>= 0.70), or `low`. A valid MRZ check digit can mark document number and date of birth `high`. An uncertain line, or a printed value that disagrees with the MRZ, sets `low`.
- `box_valid`: true only when every source line has a drawable box. A line with `box_valid` false has a zero box and must not be drawn. `uncertain` is true when a character was hard to read.

LLM-filled fields have `line_indices: []`, `box_valid: false`, and no box. Set `OCR_RETURN_BOXES=false` to keep the old fields and return `lines: []`.

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
  ],
  "lines": [
    {
      "index": 0,
      "text": "Name: JANE DOE",
      "confidence": 0.93,
      "box": { "x": 0.08, "y": 0.12, "w": 0.4, "h": 0.05 }
    },
    {
      "index": 1,
      "text": "Date of Birth: 02/03/1990",
      "confidence": 0.91,
      "box": { "x": 0.08, "y": 0.2, "w": 0.55, "h": 0.05 }
    },
    {
      "index": 2,
      "text": "Sex: F",
      "confidence": 0.9,
      "box": { "x": 0.08, "y": 0.28, "w": 0.2, "h": 0.05 }
    },
    {
      "index": 3,
      "text": "Nationality: CAN",
      "confidence": 0.92,
      "box": { "x": 0.08, "y": 0.36, "w": 0.45, "h": 0.05 }
    },
    {
      "index": 4,
      "text": "Passport No: AB123456",
      "confidence": 0.94,
      "box": { "x": 0.08, "y": 0.44, "w": 0.5, "h": 0.05 }
    }
  ],
  "field_sources": {
    "full_name": {
      "line_indices": [0],
      "source_kind": "visual",
      "confidence": 0.93,
      "level": "high"
    },
    "date_of_birth": {
      "line_indices": [1],
      "source_kind": "visual",
      "confidence": 0.91,
      "level": "high"
    },
    "gender": {
      "line_indices": [2],
      "source_kind": "visual",
      "confidence": 0.9,
      "level": "high"
    },
    "nationality": {
      "line_indices": [3],
      "source_kind": "visual",
      "confidence": 0.92,
      "level": "high"
    },
    "document_number": {
      "line_indices": [4],
      "source_kind": "visual",
      "confidence": 0.94,
      "level": "high"
    }
  },
  "image": { "original_width_px": 800, "original_height_px": 700 }
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
