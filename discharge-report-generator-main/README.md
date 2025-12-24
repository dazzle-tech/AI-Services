# 📝 Discharge Report Generation API

AI-powered discharge summary generation system using OpenAI GPT-4. Automatically creates comprehensive, professional discharge summaries from clinical documentation.

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)](https://fastapi.tiangolo.com/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-412991.svg)](https://openai.com/)

## 🎯 Overview

This system streamlines clinical documentation by automatically generating discharge summaries from patient records and clinical notes. It uses GPT-4 to synthesize information and create professional, comprehensive discharge reports.

**Key Features:**
- 🤖 **AI-Powered:** Uses OpenAI GPT-4 for intelligent text generation
- 📋 **Template-Based or Freeform:** Choose structured templates or let AI decide structure
- 🏥 **Medical Accuracy:** Generates clinically appropriate summaries
- ⚡ **Fast:** 20-40 second generation time
- 📊 **Confidence Scoring:** Each section includes confidence metrics
- 🔒 **Safe:** Requires physician review before finalization

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Usage](#-usage)
- [API Documentation](#-api-documentation)
- [Templates](#-templates)
- [Testing](#-testing)
- [Examples](#-examples)
- [Deployment](#-deployment)

## 🚀 Quick Start

```bash
# 1. Clone repository
git clone https://github.com/yourusername/discharge-report-generator.git
cd discharge-report-generator

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and add your OpenAI API key

# 5. Run server
python main.py

# 6. Test API
curl http://localhost:8000/health
```

**API Documentation:** http://localhost:8000/docs

## 📦 Installation

### Prerequisites

- Python 3.8 or higher
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))
- 1GB RAM minimum

### Step-by-Step

#### 1. Clone Repository

```bash
git clone https://github.com/yourusername/discharge-report-generator.git
cd discharge-report-generator
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
- FastAPI - Web framework
- OpenAI - GPT-4 integration
- Pydantic - Data validation
- Uvicorn - ASGI server

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

## 🎮 Usage

### Starting the Server

```bash
python main.py
```

Expected output:
```
================================================================================
📝 DISCHARGE REPORT GENERATION API - STARTING
================================================================================
🤖 AI Model: gpt-4o
📍 Server: http://0.0.0.0:8000
📚 API Docs: http://localhost:8000/docs
✅ Discharge Report Generator ready!
```

### Quick Test

**Using cURL:**
```bash
curl -X POST "http://localhost:8000/discharge/quick-generate?patient_id=DISCH001"
```

**Using Python:**
```python
import requests

response = requests.post(
    "http://localhost:8000/discharge/quick-generate",
    params={"patient_id": "DISCH001", "template_name": "standard"}
)

report = response.json()
print(report["full_report_text"])
```

**Using Test Script:**
```bash
python -m test.test_discharge_generator
```

## 📚 API Documentation

### Endpoints

#### `GET /health`
Check API health and configuration status.

**Response:**
```json
{
  "status": "healthy",
  "openai_configured": true,
  "generator_initialized": true,
  "model": "gpt-4o"
}
```

#### `POST /discharge/quick-generate`
Generate report using sample data (easiest for testing).

**Query Parameters:**
- `patient_id` (default: DISCH001)
- `template_name` (default: standard) - Options: standard, cardiac
- `generation_mode` (default: template) - Options: template, freeform

**Example:**
```bash
POST /discharge/quick-generate?patient_id=DISCH001&template_name=standard
```

#### `POST /discharge/generate-report`
Generate report with custom patient data.

**Request Body:**
```json
{
  "patient_record": {
    "patient_id": "string",
    "age": 0,
    "gender": "string",
    "admission_date": "string",
    "discharge_date": "string",
    "primary_diagnosis": "string",
    "secondary_diagnoses": [],
    "allergies": [],
    "medications_on_admission": []
  },
  "clinical_documentation": {
    "admission_notes": "string",
    "progress_notes": [],
    "procedures_performed": [],
    "lab_results": {},
    "imaging_results": [],
    "consultation_notes": []
  },
  "report_template": {
    "template_name": "string",
    "sections": [],
    "format_type": "standard"
  },
  "generation_mode": "template"
}
```

#### `GET /discharge/templates`
List available report templates.

#### `GET /discharge/sample-patients`
List available sample patients for testing.

**Interactive API Docs:** Visit http://localhost:8000/docs

## 📋 Templates

### Standard Template

General discharge summary for all patients.

**Sections:**
- Chief Complaint
- History of Present Illness
- Past Medical History
- Allergies
- Hospital Course
- Procedures Performed
- Laboratory and Imaging Findings
- Discharge Diagnosis
- Discharge Medications
- Discharge Instructions and Follow-Up

### Cardiac Template

Specialized for cardiovascular patients.

**Sections:**
- Chief Complaint
- History of Present Illness
- Cardiac Risk Factors
- Hospital Course and Interventions
- Cardiac Catheterization Findings
- Echocardiographic Findings
- Discharge Diagnosis
- Discharge Medications with Cardiac Indications
- Cardiac Rehabilitation Referral
- Follow-Up and Monitoring

### Freeform Mode

AI generates comprehensive report with its own structure based on clinical content.

## 🧪 Testing

### Automated Testing

Run the included test script:

```bash
python -m test.test_discharge_generator
```

**Test Options:**
1. Quick test (Standard template)
2. Quick test (Cardiac template)
3. Freeform generation
4. Compare templates

### Manual Testing with Postman

See [POSTMAN_TESTING_GUIDE.md](POSTMAN_TESTING_GUIDE.md) for complete guide.

**Quick Postman Test:**
```
POST http://localhost:8000/discharge/quick-generate?patient_id=DISCH001
```

### Sample Patient

**DISCH001:** 58-year-old male, Post-MI with PCI
- Primary Diagnosis: STEMI
- Procedures: Coronary angiography with PCI
- Ideal for testing cardiac summaries

## 📊 Examples

### Example 1: Quick Generate

```bash
POST /discharge/quick-generate?patient_id=DISCH001&template_name=standard
```

**Response:** (Abbreviated)
```json
{
  "patient_id": "DISCH001",
  "generation_mode": "template",
  "report_sections": [
    {
      "section_name": "Chief Complaint",
      "content": "58-year-old male presenting with acute onset severe substernal chest pain.",
      "confidence": 0.95,
      "sources": ["admission_notes"]
    },
    {
      "section_name": "Hospital Course",
      "content": "The patient was admitted with acute inferior STEMI...",
      "confidence": 0.90,
      "sources": ["progress_notes", "procedures"]
    }
  ],
  "full_report_text": "DISCHARGE SUMMARY\n\nPatient ID: DISCH001...",
  "confidence_score": 0.92,
  "requires_physician_review": true
}
```

### Example 2: Custom Patient

```python
import requests

data = {
    "patient_record": {
        "patient_id": "CUSTOM001",
        "age": 45,
        "gender": "F",
        "admission_date": "2025-12-20",
        "discharge_date": "2025-12-23",
        "primary_diagnosis": "Community-Acquired Pneumonia",
        "secondary_diagnoses": ["Asthma"],
        "allergies": ["Sulfa drugs"],
        "medications_on_admission": [
            {"name": "Albuterol Inhaler", "frequency": "PRN"}
        ]
    },
    "clinical_documentation": {
        "admission_notes": "45-year-old female with asthma presents with 5 days of productive cough, fever, and SOB.",
        "progress_notes": [
            "Day 1: Started on ceftriaxone and azithromycin. O2 sat improving.",
            "Day 2: Afebrile, O2 sat 96% on RA. Tolerating PO.",
            "Day 3: Ready for discharge."
        ],
        "lab_results": {"admission": {"wbc": 15200}, "discharge": {"wbc": 9800}}
    },
    "generation_mode": "freeform"
}

response = requests.post(
    "http://localhost:8000/discharge/generate-report",
    json=data
)

print(response.json()["full_report_text"])
```

## 🚀 Deployment (Work in Progress)

### Docker

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
docker build -t discharge-report-api .
docker run -p 8000:8000 --env-file .env discharge-report-api
```

### Cloud Deployment

**Supported Platforms:**
- AWS Lambda + API Gateway
- Google Cloud Run
- Azure Container Instances
- Heroku
- Railway

**Environment Variables for Production:**
```env
OPENAI_API_KEY=sk-prod-key
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=False
```

## 💰 Cost Estimation

### OpenAI API Costs (GPT-4o)

**Per Report:**
- Average tokens: 5,000-7,000
- Cost per report: ~$0.03-0.05

**Monthly Estimates:**
- 100 reports/day: ~$90-150/month
- 500 reports/day: ~$450-750/month
- 1,000 reports/day: ~$900-1,500/month

**Note:** Much cheaper than manual documentation time!

## 🔒 Security & Compliance

### Data Privacy
- ⚠️ **Do not send real PHI** without proper compliance review
- ⚠️ Sample data is de-identified
- ⚠️ Implement authentication for production
- ⚠️ Use HTTPS in production

### API Key Security
- ✅ Never commit `.env` file
- ✅ Use environment variables
- ✅ Rotate keys regularly
- ✅ Different keys for dev/prod

### Medical Safety
- ✅ All reports require physician review
- ✅ Mandatory disclaimer included
- ✅ Confidence scores provided
- ✅ Decision support only, not autonomous

## ⚠️ Disclaimer

**IMPORTANT:** This is an AI-powered clinical documentation tool. All generated discharge summaries are **DRAFTS** and require review and approval by a qualified healthcare professional before finalization. Do not use for final documentation without physician verification.


## 📈 Roadmap

- [ ] Add more specialized templates (Surgery, Pediatrics)
- [ ] Support for PDF export
- [ ] Integration with EHR systems
- [ ] Multi-language support
- [ ] Voice dictation input
- [ ] Real-time collaborative editing

---

**Made with ❤️ for better clinical documentation**
