# Data Flow Summary - Quick Reference

## Simple Flow Diagram

```
Client Request
    ↓
API Layer (FastAPI)
    ↓
Service Layer (Orchestrator)
    ├─→ Parser (extract structure)
    ├─→ Normalizer (standardize format)
    └─→ Conflict Resolver (compare sources)
    ↓
AI Analysis (OpenAI GPT-4.1)
    ├─→ Build prompt with all inputs
    ├─→ Call OpenAI API
    └─→ Extract JSON response
    ↓
Post-Processing
    ├─→ Validate response
    ├─→ Calculate score
    ├─→ Assign IDs
    └─→ Check for PHI
    ↓
Final Response (JSON)
```

## Key Data Transformations

### 1. Discharge Report
- **Input:** Raw text or JSON
- **After Parser:** Structured sections (patient_info, diagnoses, medications, etc.)
- **After Normalizer:** Standardized fields (medications with dose/frequency/route, vitals parsed)

### 2. Quality Analysis
- **Input:** Structured report + patient_record + onsite_docs + template + rules
- **AI Processing:** Checks completeness, consistency, safety, structure
- **Output:** Errors, missing items, inconsistencies, recommendations

### 3. Scoring
- **Start:** 100 points
- **Penalties:** Critical (-25), High (-15), Medium (-7), Low (-3)
- **Cap:** Max 50 if critical safety errors

## Request → Response Timeline

1. **0-1s:** Request received, validated
2. **1-2s:** Parsing and normalization
3. **2-62s:** AI analysis (OpenAI API call - longest step)
4. **62-63s:** Post-processing and validation
5. **63s:** Response sent

**Total:** ~30-60 seconds (mostly AI processing time)

## Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **Parser** | Extract structure from text/JSON |
| **Normalizer** | Standardize medications, vitals, sections |
| **Conflict Resolver** | Compare report vs. source documents |
| **Prompt Runner** | Build AI prompt, call OpenAI API |
| **Validator** | Validate JSON response structure |
| **Scorer** | Calculate quality score |
| **PHI Checker** | Detect and redact sensitive data |

## Input Requirements

**Required:**
- `discharge_report` (text or JSON)
- `patient_record` (dict with patient data)

**Optional:**
- `onsite_docs` (array of clinical documents)
- `report_template` (template structure)
- `quality_rules` (custom rules)

## Output Structure

```json
{
  "qa_method": "direct_qa",
  "overall_score": 0-100,
  "summary": "text summary",
  "parsed_report": {...},
  "errors": [...],
  "missing_items": [...],
  "inconsistencies": [...],
  "recommended_corrections": [...]
}
```

