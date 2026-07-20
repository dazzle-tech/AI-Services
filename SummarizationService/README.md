# 📋 Clinical Summary Service

AI-powered clinical summary generation service using OpenAI GPT-4.

## 🎯 Overview

This service generates concise, coherent clinical summaries from structured patient data using OpenAI. It's designed to rephrase patient information into professional clinical documentation while preserving all original details, abbreviations, and medical terminology.

**Key Features:**

- 🤖 **GPT-4o Powered:** Uses OpenAI GPT-4o for high-quality, fast clinical summaries
- 📝 **Clinical Summaries:** Generates professional clinical summary paragraphs
- 🏗️ **Layered Architecture:** Clean separation of concerns (API, Services, AI, Models)
- ⚡ **Fast & Reliable:** Optimized for GPT-4 with retry logic and error handling
- 🎯 **Accurate:** Preserves all medical abbreviations, numbers, and terminology
- 📋 **Structured Input:** Separate schema models for request/response
- 🔄 **Resilient:** Automatic retry with exponential backoff for transient failures
- 📊 **Usage Tracking:** Token usage monitoring for cost optimization

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [API Documentation](#-api-documentation)
- [Testing](#-testing)

## 🚀 Quick Start

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env and add your OpenAI API key

# 3. Run the server
python main.py

# 4. Test the API
curl http://localhost:8009/api/v1/health
```

**API Documentation:** http://localhost:8009/docs

## 📦 Installation

### Prerequisites

- Python 3.8 or higher
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))

### Step-by-Step

#### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

#### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set:

- `OPENAI_API_KEY`: Your OpenAI API key (required)
- `OPENAI_MODEL`: Model name (default: `qwen3:1.7b`)
- `OPENAI_TEMPERATURE`: Temperature for generation (default: `0.2`)
- `API_PORT`: Server port (default: `8009`)

## ⚙️ Configuration

### Environment Variables

| Variable             | Description                            | Default   |
| -------------------- | -------------------------------------- | --------- |
| `OPENAI_API_KEY`     | Your OpenAI API key (required)         | -         |
| `OPENAI_MODEL`       | OpenAI model name                      | `qwen3:1.7b`  |
| `OPENAI_TEMPERATURE` | Temperature for generation             | `0.2`     |
| `API_HOST`           | Server host                            | `0.0.0.0` |
| `API_PORT`           | Server port                            | `8009`    |
| `API_RELOAD`         | Auto-reload on code changes            | `False`   |

## 🎮 Usage

### Starting the Server

```bash
python main.py
```

Expected output:

```
INFO:     Starting Clinical Summary Service v1.2.0
INFO:     Using OpenAI model: qwen3:1.7b
INFO:     Uvicorn running on http://0.0.0.0:8009
INFO:     Application startup complete.
```

### Quick Test

**Using cURL:**

```bash
curl -X POST "http://localhost:8009/api/v1/summarize" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_data": {
      "Age": "45 years",
      "Gender": "Male",
      "Diagnosis": "Type 2 Diabetes",
      "Symptoms": ["Polyuria", "Polydipsia"],
      "Medications": ["Metformin 500mg BID"],
      "Allergies": ["Penicillin"]
    }
  }'
```

**Using Python:**

```python
import requests

data = {
    "patient_data": {
        "Age": "45 years",
        "Gender": "Male",
        "Diagnosis": "Type 2 Diabetes",
        "Symptoms": ["Polyuria", "Polydipsia"],
        "Medications": ["Metformin 500mg BID"],
        "Allergies": ["Penicillin"]
    }
}

response = requests.post("http://localhost:8009/api/v1/summarize", json=data)
print(response.json()["ClinicalSummary"])
```

## 📚 API Documentation

### Endpoints

#### `GET /`

Health check and service info.

**Response:**

```json
{
  "message": "Clinical Summary Service is running!",
  "version": "1.2.0",
  "model": "llama2:13b",
  "ollama_path": "C:\\Users\\user\\AppData\\Local\\Programs\\Ollama\\ollama.exe"
}
```

#### `GET /api/v1/health`

System health status.

**Response:**

```json
{
  "status": "healthy",
  "service": "clinical-summary",
  "openai_configured": true,
  "model": "qwen3:1.7b"
}
```

#### `POST /api/v1/summarize`

Generate clinical summary from patient data.

**Request Body:**

```json
{
  "request_id": "optional-request-id",
  "patient_data": {
    "Age": "45 years",
    "Gender": "Male",
    "Diagnosis": "Type 2 Diabetes",
    "Symptoms": ["Polyuria", "Polydipsia"],
    "Medications": ["Metformin 500mg BID"],
    "Surgeries": ["Appendectomy 2010"],
    "Allergies": ["Penicillin"],
    "Medical_Warnings": ["Renal impairment"],
    "Problems": ["Hypertension"],
    "Vitals": {
      "BP": "140/90",
      "HR": "72 bpm",
      "Temp": "98.6 F"
    }
  }
}
```

**Response:**

```json
{
  "request_id": "optional-request-id",
  "ClinicalSummary": "A 45-year-old male with Type 2 Diabetes. Symptoms: Polyuria, Polydipsia. Medications: Metformin 500mg BID. Past surgeries: Appendectomy 2010. Allergies: Penicillin. Medical warnings: Renal impairment. Comorbidities: Hypertension. Vital signs: BP 140/90, HR 72 bpm, Temp 98.6 F.",
  "processing_metadata": {
    "model": "qwen3:1.7b",
    "timestamp": "2025-12-24T11:20:00",
    "input_fields_count": 8
  }
}
```

**Interactive API Docs:** Visit http://localhost:8009/docs

## 🧪 Testing

### Manual Testing

```bash
# Health check
curl http://localhost:8009/api/v1/health

# Generate summary
curl -X POST http://localhost:8009/api/v1/summarize \
  -H "Content-Type: application/json" \
  -d @test_request.json
```

### Example Request (`test_request.json`)

```json
{
  "patient_data": {
    "Age": "35 years",
    "Gender": "Female",
    "Diagnosis": "Community-Acquired Pneumonia",
    "Symptoms": ["Cough", "Fever", "Shortness of breath"],
    "Medications": ["Azithromycin 500mg daily", "Albuterol inhaler PRN"],
    "Allergies": ["Sulfa drugs"],
    "Vitals": {
      "BP": "120/80",
      "HR": "95 bpm",
      "RR": "22",
      "Temp": "101.2 F",
      "SpO2": "94%"
    }
  }
}
```

## 🔒 Security & Privacy

### Configuration Security

- ✅ Never commit `.env` file
- ✅ Use environment variables for API keys
- ✅ Use HTTPS in production
- ✅ Rotate API keys regularly

### Data Privacy

- ⚠️ **Do not send real PHI** without proper compliance review
- ⚠️ Sample data should be de-identified
- ⚠️ Implement authentication for production
- ⚠️ Use HTTPS in production

## ⚠️ Important Notes

1. **OpenAI API Key Required:** Ensure you have a valid OpenAI API key set in `.env`
2. **Model Selection:** Default is `qwen3:1.7b` via local Ollama.
3. **Processing Time:** Summary generation depends on local Ollama throughput and prompt size.
4. **Accuracy:** Review generated summaries for clinical accuracy (AI is a tool, not a replacement)
5. **Cost:** Each summary uses ~200-400 tokens with GPT-4o (~$0.005-0.01 per summary)
6. **Rate Limits:** Service includes automatic retry logic for rate limit handling
7. **Network Required:** This service requires internet connectivity to OpenAI API

## 🐛 Troubleshooting

### OpenAI API Key Not Found

**Error:** `OPENAI_API_KEY must be set`

**Solution:**

1. Create `.env` file from `.env.example`
2. Add your OpenAI API key: `OPENAI_API_KEY=sk-your-key-here`
3. Verify the key is valid at https://platform.openai.com/api-keys

### API Rate Limits

**Error:** Rate limit exceeded

**Solution:**

1. Check your OpenAI usage limits
2. Implement request throttling
3. Consider upgrading your OpenAI plan

### Invalid Response

**Error:** Empty or invalid summary returned

**Solution:**

1. Check input data format
2. Verify all required fields are provided
3. Check API logs for detailed error messages

## 📈 Performance Tips

- **Recommended:** Use `qwen3:1.7b` with local Ollama for the default setup
- **Startup:** Run `ollama pull qwen3:1.7b` and `ollama run qwen3:1.7b` before calling the service
- **Temperature:** Default 0.2 is optimal for factual summaries (lower = more consistent)
- **Token Usage:** Monitor logs for token usage - typical summaries are 200-400 tokens
- **Retry Logic:** Service automatically retries on transient failures (rate limits, timeouts)
- **Batch Processing:** For multiple summaries, consider batching requests

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## ⚠️ Disclaimer

**IMPORTANT:** This is an AI-powered clinical documentation tool. All generated summaries should be reviewed by qualified healthcare professionals before use in patient care. AI systems can make errors - always verify accuracy.

## CI workflow (.github/workflows/clinical-summary-ci.yml)
---

**Made with ❤️ for better clinical documentation**
