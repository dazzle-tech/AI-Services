# Template Comparison Guide

## Purpose

This guide helps you compare actual discharge reports against the template structure to identify missing sections, incomplete fields, and formatting issues.

## Files for Comparison

1. **`template_reference_example.json`** - Complete reference example showing:
   - Template structure definition
   - Complete JSON example with all sections
   - Text format example

2. **`postman_request_example.json`** - Actual test request with template included

## How to Use for Comparison

### Step 1: Load the Template Reference

The `template_reference_example.json` file contains:
- **template_structure**: Defines all required sections and fields
- **complete_example**: Shows a fully populated JSON structure
- **text_format_example**: Shows how it should look in text format

### Step 2: Compare Your Discharge Report

When testing a discharge report, compare it against:

#### Required Sections (Must be present):
1. ✅ **patient_info** - Age, sex, dates
2. ✅ **encounter_summary** - Chief complaint, HPI, hospital course
3. ✅ **diagnoses** - Primary and secondary diagnoses
4. ✅ **medications** - Discharge medications (required)
5. ✅ **allergies** - Allergy information
6. ✅ **follow_up_and_instructions** - Follow-up and return precautions
7. ✅ **disposition** - Discharge disposition

#### Optional Sections (Nice to have):
- **procedures_and_tests** - Procedures, imaging, labs
- **vitals_and_key_results** - Vital signs and key results
- **providers_and_signoff** - Provider information

### Step 3: Check Required Fields

For each required section, verify these fields exist:

| Section | Required Fields |
|---------|----------------|
| patient_info | age, sex |
| encounter_summary | chief_complaint, hospital_course |
| diagnoses | primary_diagnosis |
| medications | discharge_medications |
| allergies | allergies |
| follow_up_and_instructions | return_precautions |
| disposition | discharge_disposition |

### Step 4: Medication Format Check

Medications should include:
- ✅ **name**: Medication name
- ✅ **dose**: Dosage (e.g., "81mg")
- ✅ **frequency**: How often (e.g., "daily", "BID")
- ✅ **route**: Administration route (e.g., "PO", "IV")
- ⚠️ **duration**: How long to take (optional but recommended)
- ⚠️ **instructions**: Special instructions (optional but recommended)

### Step 5: Use QA Service Results

The QA service will automatically compare your report against the template and report:
- **Missing Items**: Sections/fields not present
- **Errors**: Issues with completeness, consistency, safety, structure
- **Inconsistencies**: Conflicts with patient_record or onsite_docs

## Example Comparison

### ✅ Good Example (Complete)
```json
{
  "patient_info": {
    "age": 65,
    "sex": "Male",
    "admission_date": "2024-01-15",
    "discharge_date": "2024-01-18"
  },
  "medications": {
    "discharge_medications": [
      {
        "name": "Aspirin",
        "dose": "81mg",
        "frequency": "daily",
        "route": "PO"
      }
    ]
  }
}
```

### ❌ Bad Example (Missing Fields)
```json
{
  "patient_info": {
    "age": 65
    // Missing: sex, admission_date, discharge_date
  },
  "medications": {
    "discharge_medications": [
      {
        "name": "Aspirin"
        // Missing: dose, frequency, route
      }
    ]
  }
}
```

## Quick Checklist

Use this checklist when reviewing discharge reports:

- [ ] Patient info section present with age and sex
- [ ] Encounter summary with chief complaint and hospital course
- [ ] Primary diagnosis clearly stated
- [ ] Discharge medications listed with dose, frequency, route
- [ ] Allergies documented (even if NKDA)
- [ ] Return precautions included
- [ ] Discharge disposition specified
- [ ] Medication instructions clear and complete
- [ ] No conflicts with patient record
- [ ] No conflicts with onsite clinical documents

## Integration with QA Service

When you send a request to the QA service with a `report_template`, it will:

1. **Parse** the discharge report according to template structure
2. **Validate** that all required sections and fields are present
3. **Compare** against the template requirements
4. **Report** missing items and structure issues

The QA response will include:
- `missing_items`: Fields/sections required by template but not found
- `errors`: Structure and completeness issues
- `recommended_corrections`: How to fix the report

## Next Steps

1. Load `template_reference_example.json` to see the complete structure
2. Use it as a reference when creating discharge reports
3. Compare your reports against the template before submission
4. Use the QA service to automatically validate against the template

