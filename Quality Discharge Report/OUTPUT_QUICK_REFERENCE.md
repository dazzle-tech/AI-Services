# QA Output - Quick Reference

## Top-Level Fields

| Field                     | Type   | Description                            |
| ------------------------- | ------ | -------------------------------------- |
| `qa_method`               | string | Always "direct_qa"                     |
| `overall_score`           | number | Quality score 0-100 (higher is better) |
| `summary`                 | string | Human-readable summary                 |
| `parsed_report`           | object | Parsed report structure                |
| `errors`                  | array  | List of errors found                   |
| `missing_items`           | array  | Required items not present             |
| `inconsistencies`         | array  | Conflicts with source documents        |
| `recommended_corrections` | array  | Suggested fixes                        |

## Score Interpretation

- **90-100:** Excellent ✅
- **75-89:** Good ✓
- **60-74:** Acceptable ⚠️
- **0-59:** Poor ❌

## Error Severity Impact

| Severity | Score Penalty | Meaning                                      |
| -------- | ------------- | -------------------------------------------- |
| Critical | -25           | Safety issues, medication conflicts          |
| High     | -15           | Important missing items, diagnosis conflicts |
| Medium   | -7            | Missing optional fields, procedure conflicts |
| Low      | -3            | Minor formatting issues                      |

## Error Categories

| Category       | What It Checks                                         |
| -------------- | ------------------------------------------------------ |
| `completeness` | Missing required sections/fields                       |
| `consistency`  | Conflicts with patient_record or onsite_docs           |
| `safety`       | Medication errors, allergy conflicts, missing warnings |
| `structure`    | Formatting, organization, template compliance          |

## Common Sections in `parsed_report.content`

- `patient_info` - Age, sex, dates
- `encounter_summary` - Chief complaint, HPI, hospital course
- `diagnoses` - Primary and secondary diagnoses
- `medications` - Home meds, discharge meds, changes
- `allergies` - Known allergies
- `procedures_and_tests` - Procedures, imaging, labs
- `vitals_and_key_results` - Vital signs, key results
- `follow_up_and_instructions` - Follow-ups, return precautions
- `disposition` - Discharge disposition, condition
- `providers_and_signoff` - Service, author, date

## ID Formats

- Errors: `ERR-001`, `ERR-002`, ...
- Missing Items: `MISS-001`, `MISS-002`, ...
- Inconsistencies: `INC-001`, `INC-002`, ...
- Corrections: `FIX-001`, `FIX-002`, ...

## Quick Checklist

When reviewing output:

- [ ] Check `overall_score` - Is it acceptable?
- [ ] Review critical/high severity `errors`
- [ ] Check `inconsistencies` - Any conflicts?
- [ ] Review `missing_items` - What's required?
- [ ] Use `recommended_corrections` to fix issues
