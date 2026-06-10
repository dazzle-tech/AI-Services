# API Endpoints Explanation

## Overview

The ICU Summarizer API has 2 main endpoints. Each endpoint serves a specific purpose in generating ICU clinical documentation.

---

## 1. Generate Summary

### Endpoint
```
POST http://127.0.0.1:8013/v1/summaries
```

### What It Does
This is the **main endpoint** that:
1. **Receives** structured ICU flowsheet data (vitals, meds, labs, events)
2. **Processes** the data through multiple layers:
   - Normalizes flowsheet item names to clinical concepts
   - Computes trends (min/max/last values, notable changes)
   - Detects data quality issues
3. **Generates** using OpenAI LLM:
   - A markdown-formatted ICU daily summary note
   - A structured JSON summary with problem lists, assessments, plans
4. **Returns** both formats plus metadata

### Request
- **Method**: `POST`
- **Headers**: 
  - `Content-Type: application/json`
  - `X-Request-ID: your-id` (optional)
- **Body**: JSON payload with ICU data (see `test_sample_request.json`)

### Response Structure
```json
{
  "note_markdown": "# ICU Daily Summary\n\n## Patient Overview\n...",
  "note_json": {
    "one_liner": "65-year-old male with septic shock, day 3 ICU",
    "overnight_events": ["Central line placed at 02:00"],
    "objective_trends": {
      "heart_rate": "85-90 bpm, stable",
      "map": "65-70 mmHg, improving"
    },
    "problem_list": [
      {
        "problem": "Septic Shock",
        "assessment": "On norepinephrine 0.15 mcg/kg/min, MAP improving",
        "plan": "Continue vasopressor support, monitor lactate"
      },
      {
        "problem": "ARDS",
        "assessment": "On mechanical ventilation, FiO2 40%",
        "plan": "Continue current vent settings"
      }
    ],
    "lines_tubes": [
      "Central Line in place (inserted 2024-01-23)",
      "ETT in place"
    ],
    "prophylaxis": "DVT prophylaxis: Not available",
    "nutrition": "Enteral nutrition: Not available",
    "code_status": "Full Code",
    "todo": [
      "Continue norepinephrine titration",
      "Monitor lactate trend",
      "Consider weaning vent if stable"
    ],
    "watchouts": [
      "Monitor for signs of worsening shock",
      "Watch for ventilator-associated complications"
    ]
  },
  "warnings": [
    "Entry timestamp 2024-01-22T10:00:00Z outside time window, ignored"
  ],
  "source_counts": {
    "flowsheet": 7,
    "meds": 2,
    "labs": 1,
    "events": 1
  }
}
```

**Status Code**: `200 OK`

### Response Fields Explained

#### `note_markdown`
- **Type**: String (Markdown format)
- **Content**: Full ICU daily summary note in markdown
- **Use Case**: Display in markdown viewers, convert to PDF, save as text file
- **Example**: Contains sections like Patient Overview, Overnight Events, Problem List, etc.

#### `note_json`
- **Type**: Object (Structured data)
- **Content**: Same information as markdown but in structured format
- **Use Case**: Programmatic access, database storage, further processing

**Fields in `note_json`:**
- `one_liner`: Quick one-sentence patient status summary
- `overnight_events`: List of significant events during the time window
- `objective_trends`: Summary of vital sign trends (e.g., "HR: 85-90 bpm, stable")
- `problem_list`: Array of problems with assessment and plan (A&P format)
- `lines_tubes`: List of lines, tubes, and devices
- `prophylaxis`: DVT/PPI prophylaxis information
- `nutrition`: Nutrition status
- `code_status`: Code status (Full Code, DNR, etc.)
- `todo`: Action items for the day
- `watchouts`: Things to monitor/watch for

#### `warnings`
- **Type**: Array of strings
- **Content**: Data quality warnings (timestamps outside window, impossible values, etc.)
- **Use Case**: Alert users to data issues

#### `source_counts`
- **Type**: Object
- **Content**: Count of data points processed from each source
- **Use Case**: Verify data was received and processed

### Processing Flow
```
Input JSON → Normalization → Trend Analysis → Clinical Summary → LLM Generation → Response
```

### When to Use
- Generate ICU daily summary notes
- Create structured clinical documentation
- Get problem lists with assessments and plans
- Generate handoff documentation

---

## 2. Generate Presentation

### Endpoint
```
POST http://127.0.0.1:8013/v1/presentations
```

### What It Does
This endpoint:
1. **Receives** the same ICU data as Generate Summary
2. **Processes** it the same way (normalization, trends, LLM generation)
3. **Generates** a PowerPoint presentation (PPTX file) with 2-3 slides:
   - **Slide 1**: Patient Snapshot (one-liner, key vitals, code status)
   - **Slide 2**: Systems Summary (problem list with A&P)
   - **Slide 3**: To-do & Watchouts (if content exists)
4. **Returns** the PPTX file as a download

### Request
- **Method**: `POST`
- **Headers**: 
  - `Content-Type: application/json`
  - `X-Request-ID: your-id` (optional)
- **Body**: Same JSON payload as Generate Summary

### Response
- **Status Code**: `200 OK`
- **Content-Type**: `application/vnd.openxmlformats-officedocument.presentationml.presentation`
- **Content-Disposition**: `attachment; filename="icu_handoff_P12345_20240123_000000_20240123_235959.pptx"`
- **Body**: Binary PPTX file

### Response Headers
```
Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation
Content-Disposition: attachment; filename="icu_handoff_P12345_20240123_000000_20240123_235959.pptx"
X-Request-ID: your-request-id
```

### File Naming
The filename follows this pattern:
```
icu_handoff_{patient_id}_{start_timestamp}_{end_timestamp}.pptx
```

Example: `icu_handoff_P12345_20240123_000000_20240123_235959.pptx`

### Presentation Content

#### Slide 1: Snapshot
- Patient ID
- One-liner status
- Key vitals (HR, MAP, SpO2, FiO2)
- Code status

#### Slide 2: Systems Summary
- Problem list (top 5 problems)
- Each problem shows:
  - Problem name
  - Assessment (brief)
  - Plan (brief)

#### Slide 3: To-do & Watchouts
- Left side: To-do items
- Right side: Watchouts
- Only included if content exists

### How to Use in Postman
1. Send POST request
2. Click **"Send and Download"** (or regular Send)
3. Click **"Save Response"** → **"Save to a file"**
4. Save as `.pptx` file
5. Open in PowerPoint or Google Slides

### When to Use
- Generate handoff presentations for shift changes
- Create quick reference slides for rounds
- Share patient status in presentation format
- Print or display during handoffs

---

## Comparison Table

| Feature | Generate Summary | Generate Presentation |
|---------|-----------------|----------------------|
| **Method** | POST | POST |
| **Input Required** | ICU data JSON | ICU data JSON |
| **Processing** | Full processing + LLM | Full processing + LLM + PPTX |
| **Output Format** | JSON (markdown + structured) | Binary PPTX file |
| **OpenAI Used** | ✅ Yes | ✅ Yes |
| **Response Time** | 10-30 seconds | 15-35 seconds |
| **Use Case** | Documentation | Handoff slides |

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│                1. Generate Summary                      │
│  POST /v1/summaries                                      │
│  Input: ICU flowsheet data                               │
│  → Normalize concepts                                    │
│  → Compute trends                                        │
│  → Build ClinicalSummary                                │
│  → LLM generates markdown + JSON                        │
│  → Returns: note_markdown + note_json + warnings        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│             2. Generate Presentation                     │
│  POST /v1/presentations                                  │
│  Input: ICU flowsheet data (same as #1)                  │
│  → Same processing as #1                                │
│  → LLM generates structured JSON                        │
│  → PPTX generator creates slides                         │
│  → Returns: PPTX file download                           │
└─────────────────────────────────────────────────────────┘
```

---

## Example Workflow

### Typical Usage Pattern

1. **Generate Summary**
   ```
   POST /v1/summaries
   → Get markdown note and structured JSON
   → Save markdown to file or display
   → Use JSON for further processing
   ```

2. **Generate Presentation** (optional)
   ```
   POST /v1/presentations
   → Get PPTX file
   → Open in PowerPoint
   → Use for handoff meeting
   ```

---

## Error Responses

All endpoints return consistent error formats:

### 400 Bad Request (Validation Error)
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Time window end must be after start",
    "request_id": "abc-123"
  }
}
```

### 422 Unprocessable Entity (Schema Error)
```json
{
  "detail": [
    {
      "loc": ["body", "patient", "id"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 502 Bad Gateway (OpenAI Error)
```json
{
  "error": {
    "code": "OPENAI_ERROR",
    "message": "OpenAI API error: Rate limit exceeded",
    "request_id": "abc-123"
  }
}
```

---

## Key Differences

### Generate Summary vs Generate Presentation

| Aspect | Generate Summary | Generate Presentation |
|--------|----------------|---------------------|
| **Output** | Text (markdown + JSON) | Binary file (PPTX) |
| **Format** | Readable text | Visual slides |
| **Use** | Documentation, notes | Presentations, handoffs |
| **Size** | Small (JSON) | Larger (binary file) |
| **Processing** | Same | Same + PPTX generation |

### Why Two Endpoints?

- **Summary**: For text-based documentation, EMR integration, API consumption
- **Presentation**: For visual handoffs, meetings, printed materials

You can use both - they process the same data but output different formats!

---

## Tips

1. **Use Generate Summary** for most use cases (faster, more flexible)
2. **Use Generate Presentation** when you need visual slides
3. **Check warnings array** to see data quality issues
4. **Save request IDs** for troubleshooting
5. **Both POST endpoints** accept the same JSON payload format

---

## Quick Reference

```bash
# Generate Summary
POST http://127.0.0.1:8013/v1/summaries
Body: test_sample_request.json
→ JSON with note_markdown and note_json

# Generate Presentation  
POST http://127.0.0.1:8013/v1/presentations
Body: test_sample_request.json
→ PPTX file download
```
