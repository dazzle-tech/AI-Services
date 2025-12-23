# QA Output Fields Explanation

This document explains every field in the Discharge QA Service output JSON.

## Output Structure Overview

```json
{
  "qa_method": "...",
  "overall_score": 0-100,
  "summary": "...",
  "parsed_report": {...},
  "errors": [...],
  "missing_items": [...],
  "inconsistencies": [...],
  "recommended_corrections": [...]
}
```

---

## Top-Level Fields

### `qa_method`
**Type:** `string`  
**Values:** `"direct_qa"`  
**Description:** The QA method used. Currently only "direct_qa" is supported.  
**Example:**
```json
"qa_method": "direct_qa"
```

---

### `overall_score`
**Type:** `number` (float)  
**Range:** `0-100`  
**Description:** Overall quality score of the discharge report. Higher is better.  
**Scoring:**
- Starts at 100
- Subtracts points for errors:
  - Critical: -25 points
  - High: -15 points
  - Medium: -7 points
  - Low: -3 points
- Missing items: -7 points each
- Inconsistencies: Same penalty as errors based on severity
- **Special Rule:** If any critical safety errors exist, score is capped at 50

**Example:**
```json
"overall_score": 93.0
```

**Interpretation:**
- **90-100:** Excellent quality, minor issues only
- **75-89:** Good quality, some improvements needed
- **60-74:** Acceptable but requires corrections
- **0-59:** Poor quality, significant issues

---

### `summary`
**Type:** `string`  
**Description:** Human-readable summary of the QA analysis results.  
**Content:** Includes overall assessment, error counts, missing items, and general quality assessment.  
**Example:**
```json
"summary": "The discharge report is largely complete and consistent with the patient record. All critical sections are present, and there are no high-risk safety issues. Minor issues include lack of explicit home medications and incomplete medication change documentation."
```

---

## `parsed_report` Object

Contains the parsed and normalized discharge report structure.

### `parsed_report.format`
**Type:** `string`  
**Values:** `"text"` | `"json"`  
**Description:** Original format of the input discharge report.  
**Example:**
```json
"format": "text"
```

---

### `parsed_report.structure_used`
**Type:** `string`  
**Values:** `"template"` | `"standard"` | `"inferred"`  
**Description:** Which structure was used to parse the report.
- **"template":** Used provided report_template
- **"standard":** Used standard discharge report structure
- **"inferred":** Inferred structure from content

**Example:**
```json
"structure_used": "standard"
```

---

### `parsed_report.content`
**Type:** `object`  
**Description:** The parsed report content organized by sections.  
**Structure:** Contains all standard discharge report sections:

#### `parsed_report.content.patient_info`
**Fields:**
- `age` (number|null): Patient age
- `sex` (string|null): Patient sex/gender
- `admission_date` (string|null): Admission date (ISO 8601)
- `discharge_date` (string|null): Discharge date (ISO 8601)

**Example:**
```json
"patient_info": {
  "age": 65,
  "sex": "Male",
  "admission_date": "2024-01-15",
  "discharge_date": "2024-01-18"
}
```

#### `parsed_report.content.encounter_summary`
**Fields:**
- `chief_complaint` (string|null): Primary reason for admission
- `history_of_present_illness` (string|null): Detailed HPI
- `hospital_course` (string|null): Summary of hospital stay

**Example:**
```json
"encounter_summary": {
  "chief_complaint": "Chest pain and shortness of breath",
  "history_of_present_illness": "Patient presented with...",
  "hospital_course": "Patient was admitted to..."
}
```

#### `parsed_report.content.diagnoses`
**Fields:**
- `primary_diagnosis` (string|null): Primary diagnosis
- `secondary_diagnoses` (array of string): List of secondary diagnoses

**Example:**
```json
"diagnoses": {
  "primary_diagnosis": "Acute ST-elevation myocardial infarction",
  "secondary_diagnoses": ["Hypertension", "Type 2 diabetes mellitus"]
}
```

#### `parsed_report.content.medications`
**Fields:**
- `home_medications` (array): Medications patient was taking at home
- `discharge_medications` (array): Medications prescribed at discharge
- `medication_changes` (array): Changes made to medications

**Medication Object Structure:**
```json
{
  "name": "Aspirin",
  "dose": "81mg",
  "frequency": "daily",
  "route": "PO",
  "duration": "indefinite",
  "instructions": "Take with food"
}
```

**Example:**
```json
"medications": {
  "discharge_medications": [
    {
      "name": "Aspirin",
      "dose": "81mg",
      "frequency": "daily",
      "route": "PO",
      "duration": null,
      "instructions": null
    }
  ]
}
```

#### `parsed_report.content.allergies`
**Fields:**
- `allergies` (array of string): List of known allergies (empty if NKDA)
- `allergy_notes` (string|null): Additional allergy information

**Example:**
```json
"allergies": {
  "allergies": [],
  "allergy_notes": "No known drug allergies"
}
```

#### `parsed_report.content.procedures_and_tests`
**Fields:**
- `procedures` (array of string): Procedures performed
- `imaging` (array of string): Imaging studies
- `labs` (array of string): Laboratory tests

**Example:**
```json
"procedures_and_tests": {
  "procedures": ["Cardiac catheterization", "PCI"],
  "imaging": ["EKG", "Echocardiogram"],
  "labs": ["Cardiac enzymes", "Troponin"]
}
```

#### `parsed_report.content.vitals_and_key_results`
**Fields:**
- `vitals_last` (object): Last recorded vital signs
  - `bp` (string|null): Blood pressure (e.g., "120/80")
  - `hr` (string|null): Heart rate
  - `rr` (string|null): Respiratory rate
  - `temp` (string|null): Temperature
  - `o2_sat` (string|null): Oxygen saturation
- `key_results` (array of string): Key test results

**Example:**
```json
"vitals_and_key_results": {
  "vitals_last": {
    "bp": "120/80",
    "hr": "72",
    "rr": "16",
    "temp": "98.6",
    "o2_sat": "98"
  },
  "key_results": ["EKG: Normal sinus rhythm"]
}
```

#### `parsed_report.content.follow_up_and_instructions`
**Fields:**
- `follow_up_appointments` (array of string): Scheduled follow-ups
- `return_precautions` (array of string): When to return to ED
- `patient_instructions` (string|null): General instructions

**Example:**
```json
"follow_up_and_instructions": {
  "follow_up_appointments": ["Cardiology follow-up in 2 weeks"],
  "return_precautions": ["Return if chest pain worsens"],
  "patient_instructions": "Continue medications as prescribed"
}
```

#### `parsed_report.content.disposition`
**Fields:**
- `discharge_disposition` (string|null): Where patient is going (e.g., "Home", "SNF")
- `condition_on_discharge` (string|null): Patient condition (e.g., "Stable", "Improved")

**Example:**
```json
"disposition": {
  "discharge_disposition": "Home with home health services",
  "condition_on_discharge": "Stable"
}
```

#### `parsed_report.content.providers_and_signoff`
**Fields:**
- `service_department` (string|null): Responsible department
- `author_role` (string|null): Author's role
- `signoff_date` (string|null): Date of signoff

**Example:**
```json
"providers_and_signoff": {
  "service_department": "Cardiology",
  "author_role": "Attending Physician",
  "signoff_date": "2024-01-18"
}
```

---

### `parsed_report.unmapped_content`
**Type:** `array of string`  
**Description:** Content from the original report that couldn't be mapped to any section.  
**Example:**
```json
"unmapped_content": []
```

---

## `errors` Array

Array of error objects found during QA analysis.

### Error Object Structure

```json
{
  "id": "ERR-001",
  "category": "completeness|consistency|safety|structure",
  "severity": "low|medium|high|critical",
  "location": {
    "section": "medications",
    "field": "discharge_medications",
    "evidence_snippet": "..."
  },
  "issue": "Description of the issue",
  "expected": "What should be present",
  "observed": "What was actually found",
  "recommendation": "How to fix it",
  "references": [
    {
      "source": "patient_record|onsite_doc|template|quality_rule",
      "ref_id": "DOC-001",
      "note": "Additional context"
    }
  ]
}
```

### Error Fields Explained

#### `errors[].id`
**Type:** `string`  
**Format:** `"ERR-XXX"` where XXX is a 3-digit number  
**Description:** Unique identifier for the error.  
**Example:**
```json
"id": "ERR-001"
```

#### `errors[].category`
**Type:** `string`  
**Values:** 
- `"completeness"`: Missing required sections/fields
- `"consistency"`: Conflicts with source documents
- `"safety"`: Safety-critical issues
- `"structure"`: Formatting/organization issues

**Example:**
```json
"category": "completeness"
```

#### `errors[].severity`
**Type:** `string`  
**Values:** `"low"` | `"medium"` | `"high"` | `"critical"`  
**Description:** Severity level of the error.  
**Impact on Score:**
- Critical: -25 points
- High: -15 points
- Medium: -7 points
- Low: -3 points

**Example:**
```json
"severity": "low"
```

#### `errors[].location`
**Type:** `object`  
**Fields:**
- `section` (string): Section name where error was found
- `field` (string): Specific field name
- `evidence_snippet` (string): Relevant text from report

**Example:**
```json
"location": {
  "section": "medications",
  "field": "discharge_medications",
  "evidence_snippet": "Medications on Discharge: - Aspirin"
}
```

#### `errors[].issue`
**Type:** `string`  
**Description:** Brief description of what's wrong.  
**Example:**
```json
"issue": "Home medications not documented."
```

#### `errors[].expected`
**Type:** `string`  
**Description:** What should be present or correct.  
**Example:**
```json
"expected": "List of home medications prior to admission."
```

#### `errors[].observed`
**Type:** `string`  
**Description:** What was actually found (or not found).  
**Example:**
```json
"observed": "home_medications: []"
```

#### `errors[].recommendation`
**Type:** `string`  
**Description:** How to fix the issue.  
**Example:**
```json
"recommendation": "Document home medications or explicitly state if none."
```

#### `errors[].references`
**Type:** `array of objects`  
**Description:** Sources that support this error finding.  
**Reference Object:**
```json
{
  "source": "patient_record|onsite_doc|template|quality_rule",
  "ref_id": "DOC-001",
  "note": "Additional context or explanation"
}
```

**Example:**
```json
"references": [
  {
    "source": "quality_rule",
    "ref_id": "",
    "note": "Completeness: Home medications should be listed."
  }
]
```

---

## `missing_items` Array

Array of required items that are missing from the report.

### Missing Item Object Structure

```json
{
  "id": "MISS-001",
  "required_by": "template|quality_rule",
  "section": "providers_and_signoff",
  "field": "service_department",
  "why_required": "Identifies responsible service for discharge.",
  "recommendation": "Add service_department to providers_and_signoff section."
}
```

### Missing Item Fields Explained

#### `missing_items[].id`
**Type:** `string`  
**Format:** `"MISS-XXX"`  
**Description:** Unique identifier.  
**Example:**
```json
"id": "MISS-001"
```

#### `missing_items[].required_by`
**Type:** `string`  
**Values:** `"template"` | `"quality_rule"`  
**Description:** What requires this field (template or quality rule).  
**Example:**
```json
"required_by": "quality_rule"
```

#### `missing_items[].section`
**Type:** `string`  
**Description:** Section name where item is missing.  
**Example:**
```json
"section": "providers_and_signoff"
```

#### `missing_items[].field`
**Type:** `string`  
**Description:** Specific field name that's missing.  
**Example:**
```json
"field": "service_department"
```

#### `missing_items[].why_required`
**Type:** `string`  
**Description:** Explanation of why this field is required.  
**Example:**
```json
"why_required": "Identifies responsible service for discharge."
```

#### `missing_items[].recommendation`
**Type:** `string`  
**Description:** How to add the missing item.  
**Example:**
```json
"recommendation": "Add service_department to providers_and_signoff section."
```

---

## `inconsistencies` Array

Array of inconsistencies between the report and source documents.

### Inconsistency Object Structure

```json
{
  "id": "INC-001",
  "severity": "low|medium|high|critical",
  "section": "medications",
  "field": "discharge_medications",
  "report_value": "Warfarin 5mg PO daily",
  "source_value": "Aspirin 81mg PO daily, Clopidogrel 75mg PO daily",
  "source": "patient_record|onsite_doc",
  "ref_id": "DOC-001",
  "recommendation": "Verify correct medications with most recent documentation."
}
```

### Inconsistency Fields Explained

#### `inconsistencies[].id`
**Type:** `string`  
**Format:** `"INC-XXX"`  
**Description:** Unique identifier.  
**Example:**
```json
"id": "INC-001"
```

#### `inconsistencies[].severity`
**Type:** `string`  
**Values:** `"low"` | `"medium"` | `"high"` | `"critical"`  
**Description:** Severity of the inconsistency.  
**Common Severities:**
- **Critical:** Medication conflicts, allergy conflicts
- **High:** Diagnosis conflicts
- **Medium:** Procedure conflicts
- **Low:** Date conflicts, minor discrepancies

**Example:**
```json
"severity": "critical"
```

#### `inconsistencies[].section`
**Type:** `string`  
**Description:** Section where inconsistency was found.  
**Example:**
```json
"section": "medications"
```

#### `inconsistencies[].field`
**Type:** `string`  
**Description:** Specific field with inconsistency.  
**Example:**
```json
"field": "discharge_medications"
```

#### `inconsistencies[].report_value`
**Type:** `string` or `array`  
**Description:** Value found in the discharge report.  
**Example:**
```json
"report_value": "Warfarin 5mg PO daily"
```

#### `inconsistencies[].source_value`
**Type:** `string` or `array`  
**Description:** Value from the source document (patient_record or onsite_doc).  
**Example:**
```json
"source_value": "Aspirin 81mg PO daily, Clopidogrel 75mg PO daily"
```

#### `inconsistencies[].source`
**Type:** `string`  
**Values:** `"patient_record"` | `"onsite_doc"`  
**Description:** Source of the conflicting value.  
**Example:**
```json
"source": "onsite_doc"
```

#### `inconsistencies[].ref_id`
**Type:** `string`  
**Description:** Reference ID of the source document (if from onsite_doc).  
**Example:**
```json
"ref_id": "DOC-001"
```

#### `inconsistencies[].recommendation`
**Type:** `string`  
**Description:** How to resolve the inconsistency.  
**Example:**
```json
"recommendation": "Verify correct medications with most recent documentation."
```

---

## `recommended_corrections` Array

Array of recommended corrections to improve the report.

### Correction Object Structure

```json
{
  "id": "FIX-001",
  "action": "add|remove|replace|rephrase",
  "section": "medications",
  "field": "home_medications",
  "suggested_text": "Document home medications or state 'none'.",
  "rationale": "Completeness and clarity regarding patient's prior regimen."
}
```

### Correction Fields Explained

#### `recommended_corrections[].id`
**Type:** `string`  
**Format:** `"FIX-XXX"`  
**Description:** Unique identifier.  
**Example:**
```json
"id": "FIX-001"
```

#### `recommended_corrections[].action`
**Type:** `string`  
**Values:** 
- `"add"`: Add missing content
- `"remove"`: Remove incorrect content
- `"replace"`: Replace with correct content
- `"rephrase"`: Rephrase existing content

**Example:**
```json
"action": "add"
```

#### `recommended_corrections[].section`
**Type:** `string`  
**Description:** Section where correction should be made.  
**Example:**
```json
"section": "medications"
```

#### `recommended_corrections[].field`
**Type:** `string`  
**Description:** Specific field to correct.  
**Example:**
```json
"field": "home_medications"
```

#### `recommended_corrections[].suggested_text`
**Type:** `string`  
**Description:** Suggested text to add/replace.  
**Example:**
```json
"suggested_text": "Document home medications or state 'none'."
```

#### `recommended_corrections[].rationale`
**Type:** `string`  
**Description:** Why this correction is recommended.  
**Example:**
```json
"rationale": "Completeness and clarity regarding patient's prior regimen."
```

---

## Complete Example

```json
{
  "qa_method": "direct_qa",
  "overall_score": 93.0,
  "summary": "The discharge report is largely complete...",
  "parsed_report": {
    "format": "text",
    "structure_used": "standard",
    "content": {
      "patient_info": {"age": 65, "sex": "Male"},
      "diagnoses": {"primary_diagnosis": "MI"},
      "medications": {
        "discharge_medications": [
          {"name": "Aspirin", "dose": "81mg", "frequency": "daily", "route": "PO"}
        ]
      }
    },
    "unmapped_content": []
  },
  "errors": [
    {
      "id": "ERR-001",
      "category": "completeness",
      "severity": "low",
      "issue": "Home medications not documented.",
      "recommendation": "Document home medications."
    }
  ],
  "missing_items": [
    {
      "id": "MISS-001",
      "required_by": "quality_rule",
      "section": "providers_and_signoff",
      "field": "service_department",
      "recommendation": "Add service_department."
    }
  ],
  "inconsistencies": [],
  "recommended_corrections": [
    {
      "id": "FIX-001",
      "action": "add",
      "section": "medications",
      "field": "home_medications",
      "suggested_text": "Document home medications.",
      "rationale": "Required for completeness."
    }
  ]
}
```

---

## How to Use This Information

1. **Check `overall_score`** first to get a quick quality assessment
2. **Read `summary`** for a human-readable overview
3. **Review `errors`** to see what's wrong (sorted by severity)
4. **Check `missing_items`** to see what's required but missing
5. **Review `inconsistencies`** to see conflicts with source data
6. **Use `recommended_corrections`** to fix issues
7. **Examine `parsed_report.content`** to see how the report was interpreted

---

## Field Priority Guide

**High Priority (Check First):**
- `overall_score` - Overall quality
- `errors` with `severity: "critical"` or `"high"` - Critical issues
- `inconsistencies` with `severity: "critical"` - Safety conflicts

**Medium Priority:**
- `errors` with `severity: "medium"` - Important issues
- `missing_items` - Required fields missing
- `recommended_corrections` - How to improve

**Low Priority:**
- `errors` with `severity: "low"` - Minor issues
- `parsed_report.unmapped_content` - Unmapped content (usually fine)

