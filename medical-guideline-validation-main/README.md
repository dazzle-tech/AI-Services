# 🏥 Medical Guideline Validation API

AI-powered clinical decision support system that validates active medical orders against evidence-based clinical guidelines using OpenAI GPT-4.

## 🎯 Overview

This system provides intelligent, context-aware validation of clinical orders by:

- ✅ Checking orders against relevant medical guidelines (RAG-enhanced)
- 🔍 Identifying contraindications and safety risks
- 📊 Detecting missing protocol components
- 💡 Providing specific, actionable recommendations
- 🎚️ Prioritizing issues by clinical urgency (CRITICAL → ROUTINE)

**Key Features:**
- Powered by OpenAI GPT-4 for intelligent clinical reasoning
- RAG (Retrieval-Augmented Generation) over clinical guideline PDFs
- Context-aware: considers patient age, allergies, comorbidities, vitals, labs
- Structured JSON responses for easy integration
- RESTful API with FastAPI

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [API Documentation](#-api-documentation)
- [Sample Data](#-sample-data)
- [Project Structure](#-project-structure)
- [Testing](#-testing)
- [Deployment](#-deployment)
- [Contributing](#-contributing)

## 🚀 Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/medical-guideline-validation.git
cd medical-guideline-validation

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and add your OpenAI API key

# 5. Run the server
python main.py

# 6. Test the API (in a new terminal)
curl http://localhost:8000/sample-patients
```

Server will be available at: **http://localhost:8000**

API Documentation: **http://localhost:8000/docs**

## 📦 Installation

### Prerequisites

- Python 3.8+
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))
- 2GB RAM minimum (for embeddings model)

### Step-by-Step Installation

#### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/medical-guideline-validation.git
cd medical-guideline-validation
```

#### 2. Create Virtual Environment

**Mac/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows:**
```cmd
python -m venv .venv
.venv\Scripts\activate
```

#### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- FastAPI (API framework)
- OpenAI (GPT-4 integration)
- LangChain (RAG framework)
- ChromaDB (vector database)
- Sentence Transformers (embeddings)
- And more...

#### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:

```env
OPENAI_API_KEY=sk-your-actual-key-here
OPENAI_MODEL=gpt-4o
OPENAI_TEMPERATURE=0.2
```

**Important:** Never commit `.env` to Git!

## ⚙️ Configuration

All configuration is in `config.py` and `.env` file.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Your OpenAI API key (required) | - |
| `OPENAI_MODEL` | Model to use | `gpt-4o` |
| `OPENAI_TEMPERATURE` | Temperature (0.0-1.0) | `0.1` |
| `API_HOST` | Server host | `0.0.0.0` |
| `API_PORT` | Server port | `8000` |
| `API_RELOAD` | Auto-reload on code changes | `False` |

### Adding Clinical Guidelines

1. Create folder: `data/guidelines/`
2. Add PDF files: `data/guidelines/sepsis_guidelines.pdf`
3. Organize by specialty (optional):
   ```
   data/guidelines/
   ├── cardiology/
   │   └── acs_guidelines.pdf
   ├── emergency/
   │   └── sepsis_guidelines.pdf
   └── general/
       └── general_protocols.pdf
   ```
4. System auto-indexes on startup

## 🎮 Usage

### Starting the Server

```bash
python main.py
```

Expected output:
```
================================================================================
🏥 MEDICAL GUIDELINE VALIDATION API - STARTING
================================================================================
🤖 AI Model: gpt-4o
📍 Server: http://0.0.0.0:8000
📚 API Docs: http://localhost:8000/docs
================================================================================

✅ All services initialized and ready!
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

### Quick Test (Using Sample Data)

```bash
# Get list of sample patients
curl http://localhost:8000/sample-patients

# Validate Patient P003 (Septic Shock - has critical issues)
curl -X POST "http://localhost:8000/validate/quick-check" \
  -H "Content-Type: application/json" \
  -d '{"patient_id": "P003"}'
```

### Custom Validation Request

```bash
curl -X POST "http://localhost:8000/validate/guideline-check" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "12345",
    "active_orders": {
      "medications": [
        {
          "order_id": "MED001",
          "medication": "Aspirin",
          "dose": "325 mg",
          "route": "PO",
          "frequency": "Daily"
        }
      ],
      "procedures": [],
      "labs": [],
      "imaging": []
    },
    "clinical_context": {
      "working_diagnosis": "Acute Coronary Syndrome",
      "presentation": "Chest pain with ST elevations"
    },
    "patient_record": {
      "age": 65,
      "gender": "M",
      "allergies": ["Penicillin"],
      "comorbidities": ["Hypertension"],
      "vitals": {
        "bp_systolic": 140,
        "bp_diastolic": 90,
        "heart_rate": 85
      },
      "recent_labs": {}
    }
  }'
```

## 📚 API Documentation

### Endpoints

#### `GET /`
Health check and service info.

#### `GET /health`
System health status.

#### `POST /validate/guideline-check`
Full validation with custom patient data.

**Request:**
```json
{
  "patient_id": "string",
  "active_orders": {
    "medications": [...],
    "procedures": [...],
    "labs": [...],
    "imaging": [...]
  },
  "clinical_context": {...},
  "patient_record": {...},
  "specialty": "string (optional)"
}
```

**Response:**
```json
{
  "patient_id": "string",
  "check_timestamp": "ISO8601",
  "overall_severity": "critical|high|moderate|low|routine",
  "summary": "string",
  "medical_notes": [
    {
      "issue": "string",
      "reasoning": "string",
      "severity": "critical|high|moderate|low|routine",
      "recommendations": ["string"],
      "guideline_reference": "string",
      "requires_human_review": boolean
    }
  ],
  "total_issues_found": 0,
  "critical_count": 0,
  "high_count": 0,
  "moderate_count": 0,
  "routine_count": 0,
  "requires_urgent_review": boolean,
  "guidelines_consulted": ["string"]
}
```

#### `POST /validate/quick-check`
Quick validation using sample patient data.

**Request:**
```json
{
  "patient_id": "P001|P002|P003"
}
```

#### `GET /sample-patients`
List available sample patients.

#### `GET /patient-details/{patient_id}`
Get full details for a sample patient.

### Interactive API Docs

Visit **http://localhost:8000/docs** for interactive Swagger UI documentation.

## 🧪 Sample Data

Three sample patients included for testing:

### Patient P001 - Acute Coronary Syndrome (Cardiology)
- **Age:** 67, Male
- **Diagnosis:** STEMI
- **Key Issue:** Missing P2Y12 inhibitor
- **Expected:** 2-3 HIGH severity findings

### Patient P002 - Community-Acquired Pneumonia (Pulmonary)
- **Age:** 45, Female
- **Diagnosis:** CAP
- **Key Issue:** Missing atypical coverage
- **Expected:** 1 MODERATE severity finding

### Patient P003 - Septic Shock (ICU) ⭐ **BEST DEMO**
- **Age:** 72, Male
- **Diagnosis:** Septic Shock
- **Key Issues:** Multiple Hour-1 Bundle violations
- **Expected:** 5+ findings, 2-3 CRITICAL

**Recommendation:** Test with **P003** first for most dramatic demonstration.

## 📁 Project Structure

```
medical-guideline-validation/
├── main.py                          # FastAPI application
├── config.py                        # Configuration
├── requirements.txt                 # Python dependencies
├── .env                            # Environment variables (create from .env.example)
├── .env.example                    # Example environment file
├── .gitignore                      # Git ignore rules
├── README.md                       # This file
│
├── models/
│   └── schemas.py                  # Pydantic models
│
├── services/
│   ├── openai_guideline_validator.py  # AI validator (main logic)
│   ├── guidelines_service.py          # RAG guideline retrieval
│   └── sample_data.py                 # Sample patient data
│
├── data/
│   └── guidelines/                 # Clinical guideline PDFs (add your own)
│       ├── sepsis_guidelines.pdf
│       └── acs_guidelines.pdf
│
└── tests/
    └── test_validator.py           # Unit tests
```

## 🧪 Testing

### Run Test Script

```bash
python -m test.test_guidelines_validator
```

### Manual Testing with cURL

```bash
# Test 1: Health check
curl http://localhost:8000/health

# Test 2: Get sample patients
curl http://localhost:8000/sample-patients

# Test 3: Quick check Patient P003
curl -X POST http://localhost:8000/validate/quick-check \
  -H "Content-Type: application/json" \
  -d '{"patient_id": "P003"}'
```

### Expected Results

For Patient P003 (Septic Shock), expect:
- ✅ 5+ issues detected
- 🚨 2-3 CRITICAL findings
- ⚠️ 2-3 HIGH priority findings
- 📋 Surviving Sepsis Campaign guidelines consulted
- 💡 Specific recommendations for each issue

## 🚀 Deployment

### Docker Deployment (Work in Progress)

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
```

```bash
docker build -t medical-guideline-api .
docker run -p 8000:8000 --env-file .env medical-guideline-api
```

### Cloud Deployment Options

- **AWS Lambda** with API Gateway
- **Google Cloud Run**
- **Azure Container Instances**
- **Heroku**
- **Railway**

### Environment Variables for Production

```env
OPENAI_API_KEY=sk-prod-key-here
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=False
```

## 💰 Cost Estimation

### OpenAI API Costs (GPT-4o)

- **Per validation:** ~$0.02 (4,800 tokens avg)
- **100 validations/day:** ~$60/month
- **1,000 validations/day:** ~$600/month

**Note:** Much cheaper than one medical error!

## 🔒 Security

### API Key Security
- ✅ Never commit `.env` file
- ✅ Use environment variables
- ✅ Rotate keys regularly
- ✅ Use different keys for dev/prod

### Data Privacy
- ⚠️ Sample data is de-identified
- ⚠️ Do not send real PHI without compliance review
- ⚠️ Implement authentication for production
- ⚠️ Use HTTPS in production

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request


## ⚠️ Disclaimer

**IMPORTANT:** This is a clinical decision support tool only. All recommendations must be reviewed by qualified healthcare professionals before implementation. Do not use for autonomous decision-making. AI systems can make errors - always verify recommendations against current guidelines.



---

**Made with ❤️ for better clinical decision support**
