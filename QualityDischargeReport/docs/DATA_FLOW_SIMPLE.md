# Data Flow - Simple Overview

## The Journey of a Discharge Report

```
┌─────────────────────────────────────────────────────────────┐
│  1. POST Request Arrives                                     │
│     POST /discharge/qa/direct                                │
│     Body: {discharge_report, patient_record, onsite_docs...} │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  2. API Endpoint (discharge_qa.py)                          │
│     • Validates request structure                            │
│     • Extracts all input data                                │
│     • Calls service layer                                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Service Orchestrator (service.py)                        │
│     • Coordinates entire QA workflow                         │
│     • Manages all components                                 │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Parser (parser.py)                                       │
│     Input: "DISCHARGE SUMMARY\nAge: 65..."                  │
│     Process: Extract sections, fields                       │
│     Output: Structured JSON with sections                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Normalizer (normalizer.py)                              │
│     Input: "Aspirin 81mg PO daily"                           │
│     Process: Parse into {name, dose, route, frequency}      │
│     Output: Standardized medication format                   │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Prompt Builder (prompt_runner.py)                       │
│     • Loads prompt template                                  │
│     • Combines all inputs into one prompt                    │
│     • Formats as JSON strings                                │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  7. OpenAI API Call                                          │
│     • Sends prompt to GPT-4.1                                │
│     • AI analyzes report against all inputs                   │
│     • Returns JSON with errors, inconsistencies, etc.          │
│     ⏱️ Takes 30-60 seconds                                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  8. Response Validator (response_validator.py)              │
│     • Validates JSON structure                               │
│     • Checks required fields                                 │
│     • Fixes common issues                                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  9. Post-Processing (service.py)                             │
│     • Calculates quality score (0-100)                       │
│     • Generates summary text                                 │
│     • Assigns IDs (ERR-001, MISS-001, etc.)                 │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  10. PHI Security Check (anonymization_check.py)            │
│      • Scans for SSN, phone, email, names                   │
│      • Redacts if found                                      │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  11. Final Response                                          │
│      Returns JSON with:                                      │
│      • overall_score: 93                                     │
│      • summary: "..."                                        │
│      • errors: [...]                                         │
│      • missing_items: [...]                                 │
│      • inconsistencies: [...]                                │
│      • recommended_corrections: [...]                        │
└─────────────────────────────────────────────────────────────┘
```

## What Happens at Each Step?

### Step 1-2: Request Reception
- **What:** HTTP POST request arrives
- **Who:** FastAPI receives it
- **Result:** Validated request data

### Step 3-4: Parsing
- **What:** Text report → Structured data
- **Example:** 
  - Input: `"Age: 65\nSex: Male"`
  - Output: `{"patient_info": {"age": 65, "sex": "Male"}}`

### Step 5: Normalization
- **What:** Raw data → Standard format
- **Example:**
  - Input: `"Aspirin 81mg PO daily"`
  - Output: `{"name": "Aspirin", "dose": "81mg", "route": "PO", "frequency": "daily"}`

### Step 6-7: AI Analysis
- **What:** All data → AI prompt → AI analysis
- **Takes:** 30-60 seconds (slowest step)
- **Result:** JSON with errors, inconsistencies, recommendations

### Step 8-9: Validation & Scoring
- **What:** AI response → Validated → Scored
- **Calculates:** Quality score (0-100)
- **Adds:** IDs, summary text

### Step 10: Security
- **What:** Scans for PHI
- **If found:** Redacts sensitive data

### Step 11: Response
- **What:** Complete JSON response
- **Returns:** To API caller

## Key Data Transformations

| Stage | Input Format | Output Format |
|-------|-------------|---------------|
| **Parsing** | Plain text | Structured JSON |
| **Normalization** | Varied formats | Standard format |
| **AI Prompt** | JSON objects | JSON strings in prompt |
| **AI Response** | Text (may have markdown) | Validated JSON |
| **Final** | Validated JSON | HTTP JSON response |

## Time Breakdown

- **Parsing:** < 1 second
- **Normalization:** < 1 second
- **AI Analysis:** 30-60 seconds ⏱️ (bottleneck)
- **Validation:** < 1 second
- **Post-processing:** < 1 second
- **Total:** ~30-60 seconds

## Error Handling

If something fails:
1. **AI fails** → Returns fallback structure with error message
2. **Validation fails** → Fixes response and continues
3. **PHI detected** → Redacts and continues
4. **Service error** → Returns 500 with error details

## Example Flow

**Input:**
```json
{
  "discharge_report": "Age: 65\nDiagnosis: MI",
  "patient_record": {"age": 65, "diagnoses": ["MI"]}
}
```

**After Parsing:**
```json
{
  "patient_info": {"age": 65},
  "diagnoses": {"primary_diagnosis": "MI"}
}
```

**After AI Analysis:**
```json
{
  "overall_score": 85,
  "errors": [{"severity": "low", "issue": "..."}],
  "missing_items": [...]
}
```

**Final Response:**
```json
{
  "qa_method": "direct_qa",
  "overall_score": 85,
  "summary": "...",
  "parsed_report": {...},
  "errors": [{"id": "ERR-001", ...}],
  ...
}
```

