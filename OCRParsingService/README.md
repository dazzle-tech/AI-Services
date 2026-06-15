# OCR Parsing Service

FastAPI service that combines:
- OCR extraction from image files
- Structured parsing of extracted text using OpenAI

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
