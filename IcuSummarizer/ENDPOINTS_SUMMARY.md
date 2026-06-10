# API Endpoints Summary

## Available Endpoints

The ICU Summarizer API has **2 main endpoints**:

---

## 1. Generate Summary

**Endpoint:** `POST http://127.0.0.1:8013/v1/summaries`

**What it does:**
- Takes ICU flowsheet data as input
- Processes and normalizes the data
- Generates ICU daily summary using OpenAI
- Returns markdown note + structured JSON

**Output:**
- `note_markdown`: Full markdown-formatted summary
- `note_json`: Structured data (problem_list, todo, watchouts, etc.)
- `warnings`: Data quality warnings
- `source_counts`: Count of processed data points

**Use case:** Generate clinical documentation, problem lists, notes

---

## 2. Generate Presentation

**Endpoint:** `POST http://127.0.0.1:8013/v1/presentations`

**What it does:**
- Takes same ICU data as Generate Summary
- Processes it the same way
- Generates PowerPoint presentation (PPTX)
- Returns PPTX file download

**Output:**
- PPTX file with 2-3 slides:
  - Slide 1: Patient Snapshot
  - Slide 2: Systems Summary (problem list)
  - Slide 3: To-do & Watchouts

**Use case:** Generate handoff presentations, visual summaries

---

## Quick Comparison

| Feature | Generate Summary | Generate Presentation |
|---------|-----------------|----------------------|
| **Input** | ICU data JSON | ICU data JSON (same) |
| **Output** | JSON (text) | PPTX file (binary) |
| **Format** | Markdown + JSON | PowerPoint slides |
| **Use** | Documentation | Handoffs, meetings |
| **Time** | 10-30 seconds | 15-35 seconds |

---

## Both Endpoints

- Accept the same JSON payload format
- Require OpenAI API key
- Support `X-Request-ID` header
- Return consistent error formats
- Process data through the same pipeline
