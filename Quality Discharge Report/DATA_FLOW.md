# Data Flow Explanation - Discharge QA Service

## Overview

The Discharge QA Service processes discharge reports through multiple stages to validate quality, consistency, safety, and structure.

---

## High-Level Data Flow

```
┌─────────────┐
│   Client    │ (Postman, Python script, etc.)
│  Request    │
└──────┬──────┘
       │
       │ POST /discharge/qa/direct
       │ {discharge_report, patient_record, onsite_docs, template, rules}
       ▼
┌─────────────────────────────────────────────────────────────┐
│                    API Layer                                │
│  src/api/discharge_qa.py                                    │
│  - Receives HTTP request                                    │
│  - Validates request body (Pydantic models)               │
│  - Calls service layer                                      │
└────────────────────┬────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Service Orchestrator                           │
│  src/services/discharge_qa/service.py                       │
│  DischargeQAService.perform_qa()                           │
└────────────────────┬────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   Parser     │ │  Normalizer  │ │  Conflict    │
│              │ │              │ │  Resolver    │
│ Parse text   │ │ Normalize    │ │ Resolve      │
│ into struct  │ │ meds/vitals  │ │ conflicts    │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                 │
       └────────────────┼─────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              AI-Powered Analysis                            │
│  src/core/prompt_runner.py                                  │
│  - Loads prompt template                                    │
│  - Builds prompt with all inputs                            │
│  - Calls OpenAI API (GPT-4.1)                              │
│  - Returns JSON response                                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Response Processing                            │
│  - Validate JSON structure                                  │
│  - Post-process (scoring, IDs)                              │
│  - PHI detection & sanitization                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Final Response                                 │
│  {qa_method, overall_score, summary, parsed_report,         │
│   errors, missing_items, inconsistencies, corrections}       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────┐
│   Client    │
│  Response   │
└─────────────┘
```

---

## Detailed Step-by-Step Flow

### 1. **Request Reception** (`src/api/discharge_qa.py`)

**Input:**
```json
{
  "discharge_report": "text or JSON",
  "patient_record": {...},
  "onsite_docs": [...],
  "report_template": {...},
  "quality_rules": {...}
}
```

**Process:**
- FastAPI receives HTTP POST request
- Pydantic validates request structure
- Creates `QARequest` object

**Output:** Validated request object

---

### 2. **Service Orchestration** (`src/services/discharge_qa/service.py`)

**Entry Point:** `DischargeQAService.perform_qa()`

**Step 2.1: Parsing** (`src/services/discharge_qa/parser.py`)
- **Input:** Raw discharge report (text or JSON)
- **Process:**
  - Detects format (text vs JSON)
  - If text: Extracts sections using regex patterns
  - Maps to standard structure (patient_info, diagnoses, medications, etc.)
  - Handles template-based parsing if template provided
- **Output:** Structured report with sections mapped

**Step 2.2: Normalization** (`src/services/discharge_qa/normalizer.py`)
- **Input:** Parsed report sections
- **Process:**
  - **Medications:** Extracts dose, frequency, route from text
    - Example: "Aspirin 81mg PO daily" → `{name: "Aspirin", dose: "81mg", route: "PO", frequency: "daily"}`
  - **Vitals:** Parses BP, HR, RR, Temp, O2 Sat
    - Example: "BP: 120/80" → `{bp: "120/80"}`
  - **Section Names:** Normalizes to match template/standard
- **Output:** Normalized structured data

**Step 2.3: Conflict Resolution** (`src/services/discharge_qa/conflict_resolver.py`)
- **Input:** Report values + source documents
- **Process:**
  - Compares report values with patient_record and onsite_docs
  - Uses timestamps to prefer newer documents
  - Identifies conflicts (medications, diagnoses, etc.)
  - Assesses conflict severity
- **Output:** Conflict information (used later in AI analysis)

---

### 3. **AI-Powered Analysis** (`src/core/prompt_runner.py`)

**Step 3.1: Prompt Building**
- Loads prompt template from `docs/prompts/discharge_qa_direct.prompt.md`
- Combines all inputs into structured prompt:
  ```
  [Prompt Template]
  
  === INPUTS ===
  
  DISCHARGE_REPORT:
  [parsed and normalized report]
  
  PATIENT_RECORD:
  [patient data]
  
  ONSITE_DOCS:
  [clinical documents]
  
  REPORT_TEMPLATE:
  [template if provided]
  
  QUALITY_RULES:
  [completeness, consistency, safety, structure rules]
  ```

**Step 3.2: OpenAI API Call** (`src/core/openai_client.py`)
- Sends prompt to OpenAI GPT-4.1
- Temperature: 0.3 (for consistent results)
- Max tokens: 4000
- **Wait time:** 30-60 seconds

**Step 3.3: Response Extraction**
- Extracts JSON from AI response
- Handles markdown formatting if present
- Parses JSON structure

**Output:** Raw QA results JSON

---

### 4. **Response Validation** (`src/core/response_validator.py`)

**Process:**
- Validates against JSON schema (`docs/schemas/discharge_qa.schema.json`)
- Checks required fields exist
- Validates data types
- Fixes common issues if validation fails

**Output:** Validated QA results

---

### 5. **Post-Processing** (`src/services/discharge_qa/service.py`)

**Step 5.1: Scoring** (`src/services/discharge_qa/scoring.py`)
- Starts at 100 points
- Subtracts penalties:
  - Critical: -25
  - High: -15
  - Medium: -7
  - Low: -3
- Caps at 50 if critical safety errors exist
- Generates summary text

**Step 5.2: ID Assignment**
- Assigns deterministic IDs:
  - Errors: ERR-001, ERR-002, ...
  - Missing items: MISS-001, MISS-002, ...
  - Inconsistencies: INC-001, INC-002, ...
  - Corrections: FIX-001, FIX-002, ...

**Step 5.3: PHI Check** (`src/security/anonymization_check.py`)
- Scans output for PHI patterns:
  - SSN, phone numbers, emails
  - MRN, addresses, names
- Redacts if found

**Output:** Final processed QA results

---

### 6. **Response Assembly**

**Final Structure:**
```json
{
  "qa_method": "direct_qa",
  "overall_score": 93,
  "summary": "The discharge report is generally complete...",
  "parsed_report": {
    "format": "text",
    "structure_used": "standard",
    "content": {
      "patient_info": {...},
      "diagnoses": {...},
      "medications": {...},
      ...
    },
    "unmapped_content": []
  },
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

### Discharge Report Transformation

```
Raw Text
  ↓
[Parser]
  ↓
Structured Sections
  ↓
[Normalizer]
  ↓
Normalized Fields
  ↓
[AI Analysis]
  ↓
QA Results
```

### Example: Medication Processing

**Input (Text):**
```
Medications on Discharge:
- Aspirin 81mg PO daily
- Clopidogrel 75mg PO daily
```

**After Parser:**
```json
{
  "medications": {
    "discharge_medications": [
      {"name": "Aspirin 81mg PO daily"},
      {"name": "Clopidogrel 75mg PO daily"}
    ]
  }
}
```

**After Normalizer:**
```json
{
  "medications": {
    "discharge_medications": [
      {
        "name": "Aspirin",
        "dose": "81mg",
        "route": "PO",
        "frequency": "daily"
      },
      {
        "name": "Clopidogrel",
        "dose": "75mg",
        "route": "PO",
        "frequency": "daily"
      }
    ]
  }
}
```

**After AI Analysis:**
- Checked against patient_record medications
- Validated for completeness (dose, frequency present)
- Checked for allergy conflicts
- Assessed safety (ambiguous instructions)

---

## Key Components Interaction

```
┌──────────────┐
│   Parser     │──→ Extracts structure from text
└──────────────┘
       │
       ▼
┌──────────────┐
│  Normalizer  │──→ Standardizes format
└──────────────┘
       │
       ▼
┌──────────────┐
│Prompt Runner │──→ Builds AI prompt
└──────────────┘
       │
       ▼
┌──────────────┐
│  OpenAI API  │──→ Performs analysis
└──────────────┘
       │
       ▼
┌──────────────┐
│  Validator   │──→ Validates response
└──────────────┘
       │
       ▼
┌──────────────┐
│   Scorer     │──→ Calculates score
└──────────────┘
       │
       ▼
┌──────────────┐
│PHI Checker   │──→ Sanitizes output
└──────────────┘
```

---

## Error Handling Flow

```
Request
  ↓
[Validation Error?] ──→ Return 422
  ↓ No
[Service Error?] ──→ Return 500
  ↓ No
[AI API Error?] ──→ Fallback result
  ↓ No
[Validation Error?] ──→ Fix & continue
  ↓ No
Success Response
```

---

## Performance Characteristics

- **Parsing:** < 1 second
- **Normalization:** < 1 second
- **AI Analysis:** 30-60 seconds (OpenAI API call)
- **Post-processing:** < 1 second
- **Total:** ~30-60 seconds per request

---

## Data Dependencies

```
discharge_report ──┐
                    │
patient_record ─────┼──→ Service.perform_qa()
                    │
onsite_docs ────────┤
                    │
report_template ────┤
                    │
quality_rules ──────┘
```

All inputs are optional except `discharge_report` and `patient_record`.

---

## Quality Checks Flow

```
┌──────────────┐
│ Completeness │──→ Required sections/fields present?
└──────────────┘
       │
┌──────────────┐
│ Consistency  │──→ Matches patient_record & onsite_docs?
└──────────────┘
       │
┌──────────────┐
│   Safety     │──→ Medication errors? Allergy conflicts?
└──────────────┘
       │
┌──────────────┐
│  Structure   │──→ Format correct? Sections in order?
└──────────────┘
```

All checks happen in parallel during AI analysis, then results are aggregated.

