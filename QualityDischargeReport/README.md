# Discharge QA Service

A clinical discharge report quality assurance engine that validates discharge reports against patient records, onsite clinical documentation, templates, and quality rules.

## Features

- **Direct QA Mode**: Validates discharge reports directly against multiple data sources
- **Comprehensive Validation**: Checks completeness, consistency, safety, and structure
- **AI-Powered Analysis**: Uses OpenAI GPT-4.1 for intelligent report analysis
- **Structured Output**: Returns detailed JSON with errors, inconsistencies, and recommendations
- **PHI Protection**: Built-in anonymization checks to prevent PHI leakage

## Project Structure

```
discharge-qa-service/
├── src/
│   ├── main.py                    # Application entrypoint
│   ├── api/                       # API endpoints
│   ├── core/                      # Core functionality (prompt runner, OpenAI client)
│   ├── services/                  # Business logic services
│   ├── domain/                    # Domain entities and rules
│   ├── security/                  # Security and anonymization
│   └── utils/                     # Utility functions
├── docs/                          # Documentation
├── tests/                         # Test files
└── scripts/                       # Utility scripts
```

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and configure:
```bash
OPENAI_MODEL=qwen3:1.7b
OPENAI_API_KEY=your-api-key-here
```

3. Run the service:
```bash
python run_server.py
```

Or using uvicorn directly:
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

**Note:** Don't use `python src/main.py` directly - it will cause import errors. Use `run_server.py` instead.

## API Usage

### POST /discharge/qa/direct

Validates a discharge report and returns QA results.

**Request Body:**
```json
{
  "discharge_report": "...",
  "patient_record": {...},
  "onsite_docs": [...],
  "report_template": {...},
  "quality_rules": {...}
}
```

**Response:**
```json
{
  "qa_method": "direct_qa",
  "overall_score": 85,
  "summary": "...",
  "parsed_report": {...},
  "errors": [...],
  "missing_items": [...],
  "inconsistencies": [...],
  "recommended_corrections": [...]
}
```

## Quality Rules

Quality rules are defined in `docs/quality_rules/`:
- `completeness.json`: Required sections and fields
- `consistency.json`: Consistency validation rules
- `safety.json`: Safety-critical checks
- `structure.json`: Structural requirements

## Testing

Run tests:
```bash
pytest tests/
```

## Example Usage

See `example_usage.py` for a complete example of using the service programmatically.

```python
from src.services.discharge_qa.service import DischargeQAService

service = DischargeQAService()
result = service.perform_qa(
    discharge_report="...",
    patient_record={...},
    onsite_docs=[...],
    report_template={...},
    quality_rules={...}
)
```

## Environment Variables

Create a `.env` file in the project root with:

```
OPENAI_MODEL=qwen3:1.7b
OPENAI_API_KEY=sk-proj-your-api-key-here
```

## License

MIT

