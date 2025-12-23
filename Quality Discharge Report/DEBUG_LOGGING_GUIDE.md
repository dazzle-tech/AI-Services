# Debug Logging Guide

## Overview

Debug logging has been added to track medication parsing and normalization throughout the QA process.

## How to Enable Debug Logs

### Option 1: Run Test Script with Debug

```bash
python test_with_debug.py
```

This will:
- Show debug logs in the console
- Save all logs to `debug.log` file

### Option 2: Set Logging Level in Your Code

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## What Gets Logged

### 1. Parser (`parser.py`)
- When `_extract_medications` is called
- Each line being processed
- Which lines are skipped and why
- Which lines are added as medications
- Final count of extracted medications

**Example log:**
```
DEBUG - _extract_medications called with text length: 1234
DEBUG - Split into 45 lines
DEBUG -   Line 1: Skipped (empty or comment)
DEBUG -   Line 2: Added as medication: - Aspirin 81mg PO daily
DEBUG - _extract_medications returning 5 medications
```

### 2. Normalizer (`normalizer.py`)
- When `normalize_medications` is called
- Type of each medication (string, dict, etc.)
- Parsing process for each medication
- Extracted fields (dose, route, frequency)
- Final normalized result

**Example log:**
```
DEBUG - normalize_medications called with 5 items
DEBUG - Processing medication 1: <class 'dict'> - {'name': '- Aspirin 81mg PO daily'...}
DEBUG -   Type: dict, name=- Aspirin 81mg PO daily, dose=None, frequency=None
DEBUG -   Name has full string, parsing name: - Aspirin 81mg PO daily
DEBUG - _parse_medication_string called with: - Aspirin 81mg PO daily
DEBUG -   After removing dashes: Aspirin 81mg PO daily
DEBUG -   Extracted dose: 81mg
DEBUG -   Extracted route: PO
DEBUG -   Extracted frequency: daily
DEBUG -   Final parsed result: name='Aspirin', dose=81mg, route=PO, frequency=daily
```

### 3. Service (`service.py`)
- Step-by-step process flow
- When normalization happens
- Medications after normalization
- Whether medications are properly parsed
- Merge process with AI response
- Final result check

**Example log:**
```
DEBUG - Step 1: Parsing discharge report...
DEBUG - Parsed report format: text
DEBUG - Step 2: Normalizing content...
DEBUG - Medications after normalization: {...}
DEBUG - Number of discharge medications: 5
DEBUG - ✓ Medications are properly parsed (have dose/frequency)
DEBUG - Step 6: Merging normalized content with AI response...
DEBUG - Found 5 normalized discharge medications
DEBUG - Medications properly parsed: True
DEBUG - Merging normalized medications into AI content
DEBUG - Merged 5 medications
```

## Log File Location

- **File:** `debug.log` (in project root)
- **Format:** Timestamp, logger name, level, message
- **Size:** Can get large with full debug output

## Key Things to Look For

### 1. Medication Extraction
Look for:
- `_extract_medications returning X medications`
- Check if correct number of medications extracted
- Verify no section headers included

### 2. Medication Normalization
Look for:
- `✓ Medications are properly parsed` or `⚠ Medications NOT properly parsed`
- Check extracted dose, route, frequency values
- Verify name is cleaned (no dashes, proper format)

### 3. Merge Process
Look for:
- `Retrieved normalized_content: True/False`
- `Found X normalized discharge medications`
- `Medications properly parsed: True/False`
- `Merging normalized medications into AI content`

### 4. Final Result
Check:
- Medications in final `parsed_report.content.medications.discharge_medications`
- Whether they have dose, frequency, route populated
- If not, check why merge didn't happen

## Common Issues to Debug

### Issue: Medications not extracted
**Look for:**
- Lines being skipped incorrectly
- Section headers being included
- Regex patterns not matching

**Fix:** Adjust parser filtering logic

### Issue: Medications not normalized
**Look for:**
- `⚠ Medications NOT properly parsed`
- Missing dose/frequency/route extraction
- Name not being cleaned

**Fix:** Check regex patterns in `_parse_medication_string`

### Issue: Normalized medications not merged
**Look for:**
- `Retrieved normalized_content: False` (not stored)
- `Medications properly parsed: False` (check failed)
- `No normalized medications to merge`

**Fix:** Check storage and merge logic

## Filtering Logs

### View only medication-related logs:
```bash
grep -i "medication" debug.log
```

### View only errors/warnings:
```bash
grep -E "(ERROR|WARNING)" debug.log
```

### View merge process:
```bash
grep -i "merge\|step 6" debug.log
```

## Disabling Debug Logs

To disable debug logs, change logging level:

```python
import logging
logging.basicConfig(level=logging.INFO)  # or WARNING, ERROR
```

Or set in environment:
```bash
export PYTHON_LOG_LEVEL=INFO
```

## Next Steps

1. Run `python test_with_debug.py`
2. Check `debug.log` for detailed logs
3. Look for the key indicators above
4. Identify where the process is failing
5. Fix the issue based on log findings

