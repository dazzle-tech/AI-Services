# ICU Summarizer API

Production-grade REST API service for generating ICU daily summaries and handoff presentations from structured flowsheet data.

## Overview

The ICU Summarizer service processes structured ICU flowsheet data and generates:
1. **ICU Daily Summary Note** - Markdown format with structured JSON
2. **Handoff Presentation Deck** - PowerPoint (PPTX) with 2-3 slides

## Architecture

The service follows a strict layered architecture:

- **API Layer** (`app/api/*`) - REST endpoints, HTTP handling, request/response serialization
- **Application Layer** (`app/application/*`) - Use cases and orchestration
- **Domain Layer** (`app/domain/*`) - Pure clinical logic, normalization, trend analysis
- **Infrastructure Layer** (`app/infrastructure/*`) - OpenAI client, PPTX generation, config loading

## Prerequisites

- Python 3.11+
- OpenAI API key

## Installation

1. Clone the repository:
```bash
cd icu-summarizer
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

## Configuration

### Environment Variables

- `OPENAI_API_KEY` (required): Your OpenAI API key
- `MODEL_NAME` (optional): OpenAI model to use (default: `gpt-4o`)

### Concept Mappings

Edit `config/mappings.yml` to customize how flowsheet item names/codes map to canonical clinical concepts. The file uses YAML format:

```yaml
heart_rate:
  item_names:
    - "heart rate"
    - "hr"
    - "pulse"
  item_codes:
    - "HR"
    - "PULSE"
```

## Running the Service

### Development Mode

```bash
python main.py
```

Or with uvicorn directly:
```bash
uvicorn main:app --reload
```

The API will be available at `http://127.0.0.1:8013`

### Production Mode

```bash
python main.py
```

Or with uvicorn:
```bash
uvicorn main:app --host 0.0.0.0 --port 8013
```

## API Endpoints

### 1. Generate Summary

```bash
POST /v1/summaries
Content-Type: application/json
```

**Request Body:**
```json
{
  "patient": {
    "id": "P12345",
    "name": "John Doe",
    "age": 65,
    "sex": "M",
    "mrn": "MRN123456"
  },
  "encounter": {
    "id": "E789",
    "admit_time": "2024-01-20T08:00:00Z",
    "icu_day": 3
  },
  "time_window": {
    "start": "2024-01-23T00:00:00Z",
    "end": "2024-01-23T23:59:59Z"
  },
  "flowsheet": [
    {
      "timestamp": "2024-01-23T08:00:00Z",
      "item_name": "Heart Rate",
      "value": "85",
      "unit": "bpm"
    }
  ],
  "meds": [
    {
      "timestamp": "2024-01-23T08:00:00Z",
      "med_name": "Norepinephrine",
      "dose": "0.1",
      "dose_unit": "mcg/kg/min",
      "is_infusion": true,
      "rate": "0.1",
      "rate_unit": "mcg/kg/min"
    }
  ],
  "labs": [],
  "events": [],
  "lines_tubes": [
    {
      "name": "Central Line",
      "status": "in place"
    }
  ],
  "diagnoses": ["Septic Shock", "ARDS"],
  "code_status": "Full Code"
}
```

**Response:**
```json
{
  "note_markdown": "# ICU Daily Summary\n\n...",
  "note_json": {
    "one_liner": "65-year-old male with septic shock, day 3 ICU",
    "overnight_events": [],
    "objective_trends": {},
    "problem_list": [
      {
        "problem": "Septic Shock",
        "assessment": "On norepinephrine",
        "plan": "Continue vasopressor support"
      }
    ],
    "lines_tubes": ["Central Line in place"],
    "prophylaxis": "Not available",
    "nutrition": "Not available",
    "code_status": "Full Code",
    "todo": [],
    "watchouts": []
  },
  "warnings": [],
  "source_counts": {
    "flowsheet": 1,
    "meds": 1,
    "labs": 0,
    "events": 0
  }
}
```

### 2. Generate Presentation

```bash
POST /v1/presentations
Content-Type: application/json
```

**Request Body:** Same as `/v1/summaries`

**Response:** PPTX file download with filename: `icu_handoff_{patient_id}_{start}_{end}.pptx`

## Example cURL Commands

### Generate Summary
```bash
curl -X POST http://localhost:8013/v1/summaries \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: test-123" \
  -d @sample_request.json \
  -o summary_response.json
```

### Generate Presentation
```bash
curl -X POST http://localhost:8013/v1/presentations \
  -H "Content-Type: application/json" \
  -d @sample_request.json \
  -o handoff_presentation.pptx
```

## Error Handling

The API returns consistent error responses:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Error description",
    "request_id": "uuid-or-client-provided-id"
  }
}
```

**HTTP Status Codes:**
- `200` - Success
- `400` - Bad Request (validation error)
- `422` - Unprocessable Entity (schema validation, FastAPI default)
- `502` - Bad Gateway (OpenAI service error)
- `500` - Internal Server Error

## Request ID Tracking

The API supports request ID tracking:
- If client sends `X-Request-ID` header, it is preserved
- Otherwise, a UUID is generated and returned in response headers
- Request ID is included in all error responses

## Data Quality & Safety

- **Timestamp Validation**: Entries outside the time window are excluded with warnings
- **Impossible Value Detection**: Values outside physiological ranges trigger warnings
- **No Data Fabrication**: LLM is instructed to never invent data; missing data is marked as "Not available"
- **Unit Normalization**: Units are preserved when available; normalization occurs where mappings exist

## Testing

Run tests with pytest:

```bash
pytest tests/
```

## Extending Concept Mappings

To add new clinical concepts:

1. Edit `config/mappings.yml`
2. Add a new concept entry:
```yaml
new_concept:
  item_names:
    - "display name 1"
    - "display name 2"
  item_codes:
    - "CODE1"
    - "CODE2"
```

3. Update the trend engine in `app/domain/trends.py` to compute trends for the new concept
4. Restart the service

## Project Structure

```
icu-summarizer/
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── api/                    # API layer
│   │   ├── middleware.py
│   │   └── routes/
│   │       ├── summaries.py
│   │       └── presentations.py
│   ├── application/            # Application layer
│   │   ├── summarize_use_case.py
│   │   └── presentation_use_case.py
│   ├── domain/                 # Domain layer
│   │   ├── input_models.py     # ALL request models (MANDATORY)
│   │   ├── clinical_models.py
│   │   ├── normalization.py
│   │   └── trends.py
│   ├── infrastructure/         # Infrastructure layer
│   │   ├── config_loader.py
│   │   ├── openai_client.py
│   │   ├── llm_prompt.py
│   │   └── pptx_generator.py
│   └── utils/
│       ├── time_utils.py
│       └── errors.py
├── config/
│   └── mappings.yml            # Concept mappings
├── tests/
│   ├── test_trends.py
│   └── test_normalization.py
├── .env.example
├── requirements.txt
└── README.md
```

## License

[Add your license here]
