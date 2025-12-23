# Quick Start Guide - Discharge QA Service

## Prerequisites
- Python 3.8+ installed
- OpenAI API key (set in `.env` file)

## Installation

All dependencies should already be installed. If not, run:
```bash
pip install -r requirements.txt
```

## Running the Service

### Option 1: Run as API Server

Start the FastAPI server:
```bash
python src/main.py
```

The service will start on `http://localhost:8000`

**Test the API:**
- Open browser: http://localhost:8000
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

**Test with curl:**
```bash
curl -X POST "http://localhost:8000/discharge/qa/direct" \
  -H "Content-Type: application/json" \
  -d @test_request.json
```

### Option 2: Run Test Script (Recommended for First Test)

Run the simple test script:
```bash
python test_service.py
```

This will:
1. Load test data from `tests/fixtures/`
2. Run QA analysis
3. Display results
4. Save full results to `qa_output.json`

### Option 3: Run Example Script

Run the example usage script:
```bash
python example_usage.py
```

## Testing

### Unit Tests
```bash
pytest tests/unit/
```

### Integration Tests
```bash
pytest tests/integration/
```

### All Tests
```bash
pytest tests/
```

## API Request Example

Create a file `test_request.json`:
```json
{
  "discharge_report": "DISCHARGE SUMMARY\nPatient: ...",
  "patient_record": {
    "age": 65,
    "sex": "Male",
    "diagnoses": ["MI"]
  },
  "onsite_docs": [
    {
      "doc_id": "DOC-001",
      "doc_type": "progress_note",
      "timestamp": "2024-01-15T10:00:00Z",
      "department": "Cardiology",
      "content": "Patient stable...",
      "is_deidentified": true
    }
  ],
  "report_template": null,
  "quality_rules": null
}
```

Then test with:
```bash
curl -X POST "http://localhost:8000/discharge/qa/direct" \
  -H "Content-Type: application/json" \
  -d @test_request.json
```

## Troubleshooting

### Error: "OpenAI API key is required"
- Make sure `.env` file exists in project root
- Check that `OPENAI_API_KEY` is set in `.env`

### Error: Module not found
- Run: `pip install -r requirements.txt`
- Make sure you're in the project root directory

### Error: Connection timeout
- Check your internet connection
- Verify OpenAI API key is valid
- Check OpenAI API status

## Next Steps

1. Review `qa_output.json` to see full QA results
2. Customize quality rules in `docs/quality_rules/`
3. Modify test data in `tests/fixtures/`
4. Integrate with your clinical system

