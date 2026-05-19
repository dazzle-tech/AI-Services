# Nurse Task Prioritization Service

AI-powered nursing task prioritization service using OpenAI. This service receives patient monitoring data, pending nursing tasks, medication schedules, abnormal findings, and operational context, then returns a prioritized nursing task list ordered by urgency and clinical importance.

## Overview

The Nurse Task Prioritization Service helps nurses focus on the most urgent and time-sensitive actions first by combining clinical urgency (vital instability, abnormal labs, risk flags) with operational urgency (due medications, overdue tasks).

**Key Features:**

- 🤖 **GPT-4o Powered:** Uses OpenAI GPT-4o for high-quality task prioritization
- 📋 **Prioritized Task List:** Returns ranked tasks with reasons and source signals
- 🏗️ **Layered Architecture:** Clean separation of concerns (API, Services, AI, Models)
- 🔒 **Traceability:** Preserves source_signals for audit and clinical review
- ⚠️ **Safety-First:** Supports prioritization only; does not replace nursing judgment

## Quick Start

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env and add your OpenAI API key

# 3. Run the server
python main.py

# 4. Test the API
curl http://localhost:8002/api/v1/health
```

**API Documentation:** http://localhost:8002/docs

## Installation

### Prerequisites

- Python 3.11+
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))

### Local Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set OPENAI_API_KEY
python main.py
```

### Docker

```bash
# Build and run
docker-compose up --build

# Or build only
docker build -t nurse-task-prioritization-service .
docker run -p 8002:8002 -e OPENAI_API_KEY=sk-your-key nurse-task-prioritization-service
```

## Configuration

| Variable             | Description                    | Default   |
|----------------------|--------------------------------|-----------|
| `OPENAI_API_KEY`     | OpenAI API key (required)      | -         |
| `OPENAI_MODEL`       | OpenAI model name              | `gpt-4o`  |
| `OPENAI_TEMPERATURE` | Temperature for generation     | `0.2`     |
| `API_PORT`           | Server port                    | `8002`    |
| `LOG_LEVEL`          | Logging level                  | `INFO`    |

## API

### POST /api/v1/prioritize-tasks

Prioritize nursing tasks across assigned patients.

**Request Body Example:**

```json
{
  "request_id": "req-001",
  "unit_context": {
    "unit_name": "Medical Ward A",
    "shift": "day",
    "generated_at": "2026-03-16T09:00:00Z"
  },
  "nurse_context": {
    "nurse_id": "N-204",
    "assigned_rooms": ["101", "102", "103", "104"]
  },
  "patients": [
    {
      "patient_id": "P-1001",
      "room": "101",
      "patient_risk_flags": ["fall_risk"],
      "vitals": [
        {
          "name": "oxygen_saturation",
          "value": "88",
          "unit": "%",
          "timestamp": "2026-03-16T08:55:00Z"
        }
      ],
      "lab_alerts": [
        {
          "name": "potassium",
          "value": "2.9",
          "unit": "mmol/L",
          "flag": "low",
          "timestamp": "2026-03-16T08:40:00Z"
        }
      ],
      "medication_tasks": [
        {
          "task_id": "MED-1",
          "medication_name": "Insulin",
          "due_time": "2026-03-16T09:05:00Z",
          "status": "pending",
          "priority_hint": "time_sensitive"
        }
      ],
      "nursing_tasks": [
        {
          "task_id": "TASK-1",
          "title": "Reassess oxygen therapy",
          "due_time": "2026-03-16T09:00:00Z",
          "status": "pending"
        }
      ],
      "notes": [
        {
          "type": "nurse_note",
          "timestamp": "2026-03-16T08:30:00Z",
          "text": "Patient short of breath during ambulation."
        }
      ]
    }
  ]
}
```

**Response Example:**

```json
{
  "request_id": "req-001",
  "prioritized_tasks": [
    {
      "rank": 1,
      "patient_id": "P-1001",
      "room": "101",
      "task_id": "TASK-1",
      "task_type": "clinical_reassessment",
      "title": "Reassess oxygen therapy",
      "reason": "Oxygen saturation is 88% with shortness of breath and tachycardia.",
      "urgency": "critical",
      "recommended_timeframe": "immediate",
      "source_signals": [
        "oxygen_saturation=88%",
        "heart_rate=118 bpm",
        "note: shortness of breath during ambulation"
      ]
    }
  ],
  "summary": "Task prioritization generated successfully.",
  "processing_metadata": {
    "model": "gpt-4o",
    "timestamp": "2026-03-16T09:05:00.000000",
    "patient_count": 1,
    "task_count": 1
  }
}
```

### GET /api/v1/health

Health check with OpenAI configuration status.

## Postman Collection

1. Open Postman
2. Import → Upload Files
3. Select `postman/NurseTaskPrioritizationService.postman_collection.json`
4. Ensure the service is running on `http://localhost:8002` (or update the `baseUrl` variable)

The collection includes:
- Health Check
- Prioritize Tasks (Minimal)
- Prioritize Tasks (Full Example)
- Prioritize Tasks (Invalid Payload)

Test scripts are included for automated validation.

## Testing

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit/

# Run integration tests only
pytest tests/integration/
```

## Safety & Disclaimer

- This service supports **prioritization only** and does not replace nursing judgment.
- It does not issue definitive treatment decisions.
- When data is insufficient or conflicting, the service is conservative and mentions uncertainty in the reason field.
- All output preserves traceability through `source_signals`.
- Do not send real PHI without proper compliance review.

---

**Made for better nursing workflow prioritization**
