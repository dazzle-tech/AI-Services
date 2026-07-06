# Data Flow Documentation

## Overview

This document explains how data flows through the Discharge QA Service from API request to final response.

---

## High-Level Flow Diagram

```
API Request (POST /discharge/qa/direct)
    ↓
[1] API Endpoint (discharge_qa.py)
    ↓
[2] Service Orchestrator (service.py)
    ↓
[3] Parser (parser.py) → Parse & Structure Report
    ↓
[4] Normalizer (normalizer.py) → Normalize Content
    ↓
[5] Prompt Runner (prompt_runner.py) → Build AI Prompt
    ↓
[6] OpenAI API → AI Analysis
    ↓
[7] Response Validator (response_validator.py) → Validate JSON
    ↓
[8] Post-Processing (scoring, conflict resolution, ID assignment)
    ↓
[9] PHI Check (anonymization_check.py) → Security Check
    ↓
[10] API Response (JSON)
```

---

## Detailed Step-by-Step Flow

### Step 1: API Request Received

**Location:** `src/api/discharge_qa.py`

**Input:**
```json
{
  "discharge_report": "DISCHARGE SUMMARY...",
  "patient_record": {...},
  "onsite_docs": [...],
  "report_template": {...},
  "quality_rules": {...}
}
```

**Process:**
- FastAPI receives POST request at `/discharge/qa/direct`
- Pydantic validates request structure (`QARequest` model)
- Extracts all input fields
- Calls `DischargeQAService.perform_qa()`

**Output:** Validated request data passed to service layer

---

### Step 2: Service Orchestration

**Location:** `src/services/discharge_qa/service.py` → `perform_qa()`

**Process:**
1. Initialize all components (parser, normalizer, prompt runner, etc.)
2. Coordinate the QA workflow
3. Handle errors and fallbacks

**Key Method:** `perform_qa()` orchestrates the entire process

---

### Step 3: Parse Discharge Report

**Location:** `src/services/discharge_qa/parser.py` → `DischargeReportParser.parse()`

**Input:** 
- Raw discharge report (text or JSON)
- Optional report template

**Process:**
1. **Detect Format:**
   - Check if input is string (text) or dict (JSON)
   - Try parsing string as JSON first

2. **Parse Text Reports:**
   - Extract sections using regex patterns
   - Map to standard structure:
     - `patient_info` (age, sex, dates)
     - `encounter_summary` (chief complaint, HPI, hospital course)
     - `diagnoses` (primary, secondary)
     - `medications` (discharge meds, home meds)
     - `allergies`
     - `vitals_and_key_results`
     - `follow_up_and_instructions`
     - `disposition`
     - `providers_and_signoff`

3. **Normalize Structure:**
   - Map section names to standard format
   - Fill in missing sections with empty structures
   - Track unmapped content

**Output:**
```python
{
  "format": "text" | "json",
  "structure_used": "template" | "standard" | "inferred",
  "content": {
    "patient_info": {...},
    "encounter_summary": {...},
    ...
  },
  "unmapped_content": []
}
```

---

### Step 4: Normalize Content

**Location:** `src/services/discharge_qa/normalizer.py` → `_normalize_content()`

**Process:**

1. **Normalize Medications:**
   - Parse medication strings: "Aspirin 81mg PO daily"
   - Extract: name, dose, frequency, route, duration, instructions
   - Convert to structured format:
     ```json
     {
       "name": "Aspirin",
       "dose": "81mg",
       "frequency": "daily",
       "route": "PO"
     }
     ```

2. **Normalize Vitals:**
   - Parse vitals strings: "BP: 120/80, HR: 72"
   - Extract: bp, hr, rr, temp, o2_sat
   - Convert to standard format:
     ```json
     {
       "bp": "120/80",
       "hr": "72",
       "rr": "16",
       "temp": "98.6",
       "o2_sat": "98"
     }
     ```

3. **Normalize Section Names:**
   - Map variations to standard names
   - "Patient Demographics" → "patient_info"
   - "Diagnosis" → "diagnoses"

**Output:** Fully normalized report structure

---

### Step 5: Build AI Prompt

**Location:** `src/core/prompt_runner.py` → `run_qa()` → `_build_prompt()`

**Process:**

1. **Load Prompt Template:**
   - Read `docs/prompts/discharge_qa_direct.prompt.md`
   - Contains instructions for AI analysis

2. **Assemble Prompt:**
   ```
   [Prompt Template]
   
   === INPUTS ===
   
   DISCHARGE_REPORT:
   [discharge report content]
   
   PATIENT_RECORD:
   [patient record JSON]
   
   ONSITE_DOCS:
   [onsite documents JSON]
   
   REPORT_TEMPLATE:
   [template JSON if provided]
   
   QUALITY_RULES:
   [quality rules JSON if provided]
   
   === END INPUTS ===
   
   Now perform Direct QA and return ONLY JSON output.
   ```

3. **Format All Inputs:**
   - Convert all data structures to JSON strings
   - Include all context needed for analysis

**Output:** Complete prompt string ready for OpenAI API

---

### Step 6: AI Analysis (OpenAI API)

**Location:** `src/core/openai_client.py` → `complete()`

**Process:**

1. **Initialize OpenAI Client:**
   - Load API key from `.env` file
   - Set model (default: `qwen3:1.7b`)

2. **Send Request:**
   - POST to OpenAI Chat Completions API
   - Include system message (if provided)
   - Include user prompt with all inputs
   - Set temperature: 0.3 (for consistent results)
   - Set max_tokens: 4000

3. **Receive Response:**
   - AI analyzes discharge report
   - Validates against patient record, onsite docs, rules
   - Generates structured JSON output

**Output:** Raw AI response text (should be JSON)

---

### Step 7: Extract & Parse AI Response

**Location:** `src/core/prompt_runner.py` → `run_qa()`

**Process:**

1. **Extract JSON:**
   - Use `extract_json_from_text()` utility
   - Handles cases where AI adds markdown or extra text
   - Finds JSON block in response

2. **Parse JSON:**
   - Convert string to Python dict
   - Validate basic structure

**Output:** Parsed JSON dictionary

---

### Step 8: Validate Response

**Location:** `src/core/response_validator.py` → `validate()`

**Process:**

1. **Schema Validation:**
   - Load JSON schema from `docs/schemas/discharge_qa.schema.json`
   - Validate response structure using `jsonschema`
   - Check required fields:
     - `qa_method`
     - `overall_score`
     - `summary`
     - `parsed_report`
     - `errors`
     - `missing_items`
     - `inconsistencies`
     - `recommended_corrections`

2. **Fix Common Issues:**
   - Add missing required fields
   - Ensure score is 0-100
   - Ensure arrays exist (even if empty)

**Output:** Validated and fixed response dictionary

---

### Step 9: Post-Processing

**Location:** `src/services/discharge_qa/service.py` → `_post_process()`

**Process:**

1. **Recalculate Score (if needed):**
   - Use `QAScorer.calculate_score()`
   - Start at 100
   - Subtract penalties:
     - Critical: -25
     - High: -15
     - Medium: -7
     - Low: -3
   - Cap at 50 if critical safety errors exist
   - Ensure score is 0-100

2. **Generate Summary (if missing):**
   - Use `QAScorer.generate_summary()`
   - Count errors by severity
   - Create human-readable summary

3. **Assign IDs:**
   - Assign deterministic IDs:
     - Errors: `ERR-001`, `ERR-002`, ...
     - Missing items: `MISS-001`, `MISS-002`, ...
     - Inconsistencies: `INC-001`, `INC-002`, ...
     - Corrections: `FIX-001`, `FIX-002`, ...

**Output:** Post-processed response with scores and IDs

---

### Step 10: Conflict Resolution (Future Enhancement)

**Location:** `src/services/discharge_qa/conflict_resolver.py`

**Process:**
- Compare report values with patient record and onsite docs
- Identify conflicts
- Prefer newer documents (by timestamp)
- Assess conflict severity
- Add to inconsistencies list

**Note:** Currently handled by AI, but can be enhanced with explicit conflict resolution

---

### Step 11: PHI Security Check

**Location:** `src/security/anonymization_check.py` → `check_output()`

**Process:**

1. **Detect PHI:**
   - Scan output for PHI patterns:
     - SSN: `\d{3}-\d{2}-\d{4}`
     - Phone: `\d{3}[-.]?\d{3}[-.]?\d{4}`
     - Email: `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}`
     - MRN: `MRN[:\s]*\d+`
     - Address: Street addresses
     - Names: `Mr/Mrs/Ms/Dr [Name]`

2. **Sanitize if Found:**
   - Replace with `[REDACTED-*]` placeholders
   - Log detection for audit

**Output:** Sanitized response (if PHI detected)

---

### Step 12: Final Response Assembly

**Location:** `src/services/discharge_qa/service.py` → `perform_qa()`

**Process:**

1. **Merge Components:**
   - Include parsed report structure
   - Include AI analysis results
   - Include post-processing results

2. **Ensure Completeness:**
   - All required fields present
   - All arrays initialized
   - All IDs assigned

**Output:** Complete QA result dictionary

---

### Step 13: API Response

**Location:** `src/api/discharge_qa.py` → `perform_direct_qa()`

**Process:**

1. **Convert to Response Model:**
   - Use Pydantic `QAResponse` model
   - Validates structure
   - Serializes to JSON

2. **Return HTTP Response:**
   - Status: 200 OK
   - Content-Type: application/json
   - Body: Complete QA results

**Final Output:**
```json
{
  "qa_method": "direct_qa",
  "overall_score": 93,
  "summary": "The discharge report is generally complete...",
  "parsed_report": {...},
  "errors": [
    {
      "id": "ERR-001",
      "category": "safety",
      "severity": "low",
      "issue": "...",
      ...
    }
  ],
  "missing_items": [...],
  "inconsistencies": [...],
  "recommended_corrections": [...]
}
```

---

## Data Transformations

### Input → Parsed
- **Text report** → **Structured sections** with extracted fields

### Parsed → Normalized
- **Raw fields** → **Standardized format** (medications, vitals, sections)

### Normalized → AI Prompt
- **Structured data** → **JSON strings** in prompt template

### AI Response → Validated
- **Raw AI text** → **Validated JSON structure**

### Validated → Scored
- **AI results** → **Scored results** with calculated quality score

### Scored → Final
- **Scored results** → **Final response** with IDs, sanitization, complete structure

---

## Error Handling Flow

```
Request → Validation Error → 422 Response
    ↓
Service Error → Try/Catch → Fallback Result
    ↓
AI Error → Exception → Fallback Structure
    ↓
Validation Error → Fix Response → Continue
    ↓
PHI Detected → Sanitize → Continue
    ↓
Success → Return Response
```

---

## Key Components & Their Roles

| Component | Purpose | Input | Output |
|-----------|---------|-------|--------|
| **API Endpoint** | Receive & validate requests | HTTP POST | Validated request data |
| **Parser** | Extract structure from text | Raw report | Structured sections |
| **Normalizer** | Standardize formats | Structured data | Normalized data |
| **Prompt Runner** | Build AI prompt | All inputs | Complete prompt |
| **OpenAI Client** | Call AI API | Prompt | AI response |
| **Validator** | Validate JSON structure | AI response | Validated JSON |
| **Scorer** | Calculate quality score | Errors/items | Score & summary |
| **PHI Checker** | Security validation | Final response | Sanitized response |

---

## Performance Considerations

1. **AI API Call:** 30-60 seconds (bottleneck)
2. **Parsing:** < 1 second
3. **Normalization:** < 1 second
4. **Validation:** < 1 second
5. **Post-processing:** < 1 second

**Total:** ~30-60 seconds (mostly AI processing)

---

## Caching Opportunities

- Parsed report structure (if same report)
- Normalized content (if same report)
- Quality rules (load once, reuse)

---

## Future Enhancements

1. **Async Processing:** Make AI calls async
2. **Caching:** Cache parsed/normalized results
3. **Batch Processing:** Process multiple reports
4. **Streaming:** Stream results as they're generated
5. **Conflict Resolution:** Explicit conflict detection before AI

