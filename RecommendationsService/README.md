# Clinical Recommendations Service

An AI-powered clinical recommendations service that generates evidence-based, actionable clinical recommendations from patient context using OpenAI GPT-4.

## Overview

This service analyzes patient data (demographics, diagnosis, symptoms, medications, allergies, vitals, etc.) and generates comprehensive clinical recommendations including:
- **Medication recommendations** - Drug therapy suggestions
- **Diagnostic recommendations** - Tests and imaging suggestions
- **Treatment recommendations** - Treatment plan suggestions
- **Monitoring recommendations** - Follow-up and monitoring needs
- **Lifestyle recommendations** - Lifestyle modifications
- **Referral recommendations** - Specialist referrals
- **General recommendations** - Other clinical guidance

Each recommendation includes:
- Priority level (critical, high, moderate, low, routine)
- Detailed description and rationale
- Actionable steps
- Evidence level
- Contraindications
- Monitoring requirements
- Follow-up recommendations

## Architecture

The service follows a layered architecture:

```
recommendations_service/
├── app/
│   ├── api/              # FastAPI routes and endpoints
│   ├── core/             # Configuration and settings
│   ├── models/           # Pydantic schemas (request/response)
│   ├── services/         # Business logic layer
│   └── ai/               # OpenAI client and prompts
├── main.py               # FastAPI application entry point
├── requirements.txt      # Python dependencies
└── .env.example          # Environment variables template
```

### Key Components

1. **API Layer** (`app/api/routes.py`)
   - RESTful endpoints for recommendations
   - Request validation
   - Error handling

2. **Service Layer** (`app/services/recommendations_service.py`)
   - Orchestrates recommendation generation
   - Processes requests and builds responses
   - Calculates priority breakdowns

3. **AI Layer** (`app/ai/`)
   - `client.py`: OpenAI API client with retry logic
   - `prompts.py`: Prompt templates for GPT-4

4. **Models** (`app/models/schemas.py`)
   - Request/response schemas
   - Data validation

5. **Configuration** (`app/core/config.py`)
   - Environment-based settings
   - OpenAI configuration

## Installation

### 1. Prerequisites
- Python 3.8 or higher
- OpenAI API key

### 2. Install Dependencies

```bash
cd recommendations_service
python -m venv venv

# On Windows:
.\venv\Scripts\Activate.ps1

# On Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure Environment

Create a `.env` file in the `recommendations_service` directory:

```bash
# Copy the example file
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:

```env
# OpenAI Configuration
OPENAI_API_KEY=sk-your-actual-openai-api-key-here
OPENAI_MODEL=qwen3:1.7b
OPENAI_TEMPERATURE=0.3
OPENAI_MAX_TOKENS=1500

# API Server Configuration
API_HOST=0.0.0.0
API_PORT=8004
API_RELOAD=False

# Service Configuration
ENABLE_USAGE_TRACKING=True
MAX_INPUT_LENGTH=10000
```

## Running the Service

### Development Mode

```bash
# Activate virtual environment first
.\venv\Scripts\Activate.ps1  # Windows
# or
source venv/bin/activate     # Linux/Mac

# Run the server
python main.py
```

The service will start on `http://localhost:8004`

### Production Mode

```bash
# Using uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8004

# Or with gunicorn (for production)
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8004
```

## API Endpoints

### 1. Root Endpoint
```
GET /
```
Returns service status and version information.

**Response:**
```json
{
  "message": "Clinical Recommendations Service is running!",
  "version": "1.0.0",
  "model": "qwen3:1.7b",
  "docs": "/docs"
}
```

### 2. Generate Recommendations
```
POST /api/v1/recommendations
```

Generates clinical recommendations from patient context.

**Request Body:**
```json
{
  "request_id": "optional-request-id",
  "patient_context": {
    "age": "45 years",
    "gender": "Male",
    "diagnosis": "Type 2 Diabetes",
    "symptoms": ["Increased thirst", "Frequent urination", "Fatigue"],
    "medications": ["Metformin 500mg twice daily"],
    "allergies": ["Penicillin"],
    "comorbidities": ["Hypertension"],
    "vitals": {
      "BP": "140/90 mmHg",
      "HR": "78 bpm",
      "Temperature": "98.6°F"
    },
    "lab_results": {
      "HbA1c": "8.2%",
      "Fasting Glucose": "180 mg/dL"
    },
    "clinical_notes": "Patient reports poor medication adherence"
  },
  "recommendation_types": ["medication", "monitoring", "lifestyle"],
  "focus_areas": ["medication optimization", "diabetes management"]
}
```

**Response:**
```json
{
  "request_id": "req_20241224_123456",
  "recommendations": [
    {
      "recommendation_id": "rec_1",
      "type": "medication",
      "title": "Optimize Metformin Dosing",
      "description": "Consider increasing Metformin to 1000mg twice daily...",
      "rationale": "Current HbA1c of 8.2% indicates suboptimal glycemic control...",
      "priority": "high",
      "actionable_steps": [
        "Increase Metformin to 1000mg twice daily",
        "Monitor for gastrointestinal side effects",
        "Recheck HbA1c in 3 months"
      ],
      "evidence_level": "Strong",
      "contraindications": [],
      "monitoring_requirements": "Monitor HbA1c, renal function, and B12 levels",
      "follow_up": "Follow-up in 3 months to assess glycemic control"
    }
  ],
  "summary": "Generated 3 clinical recommendations focusing on medication optimization...",
  "total_recommendations": 3,
  "priority_breakdown": {
    "critical": 0,
    "high": 2,
    "moderate": 1,
    "low": 0,
    "routine": 0
  },
  "processing_metadata": {
    "model": "qwen3:1.7b",
    "timestamp": "2024-12-24T12:34:56",
    "provider": "openai"
  }
}
```

### 3. Health Check
```
GET /api/v1/health
```

Returns service health status.

**Response:**
```json
{
  "status": "healthy",
  "service": "clinical-recommendations",
  "provider": "openai",
  "openai_configured": true,
  "api_accessible": true,
  "model": "qwen3:1.7b",
  "version": "1.0.0"
}
```

## API Documentation

Once the service is running, you can access:
- **Swagger UI**: `http://localhost:8004/docs`
- **ReDoc**: `http://localhost:8004/redoc`

## Testing with Postman

### Quick Test Request

1. **Method**: POST
2. **URL**: `http://localhost:8004/api/v1/recommendations`
3. **Headers**: 
   ```
   Content-Type: application/json
   ```
4. **Body** (raw JSON):
```json
{
  "patient_context": {
    "age": "65 years",
    "gender": "Female",
    "diagnosis": "Hypertension",
    "symptoms": ["Headache", "Dizziness"],
    "medications": ["Lisinopril 10mg daily"],
    "allergies": [],
    "comorbidities": ["Type 2 Diabetes"],
    "vitals": {
      "BP": "160/95 mmHg",
      "HR": "82 bpm"
    }
  },
  "recommendation_types": ["medication", "monitoring"]
}
```

## Recommendation Types

Available recommendation types:
- `medication` - Drug therapy recommendations
- `diagnostic` - Diagnostic test recommendations
- `treatment` - Treatment plan recommendations
- `monitoring` - Monitoring and follow-up recommendations
- `lifestyle` - Lifestyle modification recommendations
- `referral` - Specialist referral recommendations
- `general` - General clinical recommendations

## Priority Levels

- `critical` - Immediate action required
- `high` - Urgent, address soon
- `moderate` - Important, address in near term
- `low` - Consider when appropriate
- `routine` - Standard care

## Error Handling

The service handles various error scenarios:
- **400 Bad Request**: Invalid input data
- **500 Internal Server Error**: Processing failures
- **Rate Limiting**: Automatic retry with exponential backoff
- **API Timeouts**: Retry logic with configurable delays

## Configuration Options

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key (required) | - |
| `OPENAI_MODEL` | OpenAI model to use | `qwen3:1.7b` |
| `OPENAI_TEMPERATURE` | Model temperature | `0.3` |
| `OPENAI_MAX_TOKENS` | Max tokens in response | `1500` |
| `API_HOST` | Server host | `0.0.0.0` |
| `API_PORT` | Server port | `8004` |
| `API_RELOAD` | Enable auto-reload | `False` |
| `ENABLE_USAGE_TRACKING` | Track token usage | `True` |

## Logging

The service uses Python's logging module. Logs include:
- Request processing
- API calls to OpenAI
- Token usage
- Errors and warnings

Log level can be configured in `main.py`.

## Security Considerations

1. **API Key**: Never commit `.env` file with real API keys
2. **Rate Limiting**: Consider adding rate limiting middleware
3. **Input Validation**: All inputs are validated using Pydantic
5. **Error Messages**: Avoid exposing sensitive information in error messages

## Troubleshooting

### Service won't start
- Check that `.env` file exists and contains `OPENAI_API_KEY`
- Verify Python version (3.8+)
- Ensure all dependencies are installed: `pip install -r requirements.txt`

### API returns errors
- Verify OpenAI API key is valid
- Check API rate limits
- Review logs for detailed error messages

### Recommendations are empty
- Check that patient context includes required fields (age, gender, diagnosis)
- Verify recommendation types are valid
- Review OpenAI API response in logs

## Next Steps

- Add unit and integration tests
- Create Postman collection
- Add deployment configuration (Docker, DigitalOcean)
- Implement caching for common scenarios
- Add metrics and monitoring

## CI workflow (.github/workflows/clinical-recommendadtions-ci.yml)

## License

[Your License Here]

