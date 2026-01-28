# Test Example for ICU Summarizer API

## Quick Test Example

Use this JSON payload to test the `/v1/summaries` endpoint:

### Using Postman:

1. **Method:** `POST`
2. **URL:** `http://127.0.0.1:8000/v1/summaries` (or `http://127.0.0.1:8001/v1/summaries` if port 8000 is busy)
3. **Headers:**
   - `Content-Type: application/json`
   - `X-Request-ID: test-123` (optional)
4. **Body:** Select "raw" and "JSON", then paste the JSON below:

```json
{
  "patient": {
    "id": "P12345",
    "name": "John Doe",
    "age": 65,
    "sex": "M",
    "mrn": "MRN123456"
  },
  "encounter": {
    "id": "E789",
    "admit_time": "2024-01-20T08:00:00Z",
    "icu_day": 3
  },
  "time_window": {
    "start": "2024-01-23T00:00:00Z",
    "end": "2024-01-23T23:59:59Z"
  },
  "flowsheet": [
    {
      "timestamp": "2024-01-23T08:00:00Z",
      "item_name": "Heart Rate",
      "value": "85",
      "unit": "bpm"
    },
    {
      "timestamp": "2024-01-23T12:00:00Z",
      "item_name": "Heart Rate",
      "value": "90",
      "unit": "bpm"
    },
    {
      "timestamp": "2024-01-23T18:00:00Z",
      "item_name": "Heart Rate",
      "value": "88",
      "unit": "bpm"
    },
    {
      "timestamp": "2024-01-23T10:00:00Z",
      "item_name": "Mean Arterial Pressure",
      "value": "65",
      "unit": "mmHg"
    },
    {
      "timestamp": "2024-01-23T14:00:00Z",
      "item_name": "Mean Arterial Pressure",
      "value": "70",
      "unit": "mmHg"
    },
    {
      "timestamp": "2024-01-23T16:00:00Z",
      "item_name": "Oxygen Saturation",
      "value": "95",
      "unit": "%"
    },
    {
      "timestamp": "2024-01-23T16:00:00Z",
      "item_name": "FiO2",
      "value": "40",
      "unit": "%"
    }
  ],
  "meds": [
    {
      "timestamp": "2024-01-23T08:00:00Z",
      "med_name": "Norepinephrine",
      "dose": "0.1",
      "dose_unit": "mcg/kg/min",
      "is_infusion": true,
      "rate": "0.1",
      "rate_unit": "mcg/kg/min"
    },
    {
      "timestamp": "2024-01-23T12:00:00Z",
      "med_name": "Norepinephrine",
      "dose": "0.15",
      "dose_unit": "mcg/kg/min",
      "is_infusion": true,
      "rate": "0.15",
      "rate_unit": "mcg/kg/min"
    }
  ],
  "labs": [
    {
      "timestamp": "2024-01-23T06:00:00Z",
      "lab_name": "Lactate",
      "value": "2.5",
      "unit": "mmol/L",
      "ref_range": "0.5-2.2"
    }
  ],
  "events": [
    {
      "timestamp": "2024-01-23T02:00:00Z",
      "type": "Procedure",
      "description": "Central line placed"
    }
  ],
  "lines_tubes": [
    {
      "name": "Central Line",
      "status": "in place",
      "inserted_time": "2024-01-23T02:00:00Z"
    },
    {
      "name": "ETT",
      "status": "in place"
    }
  ],
  "diagnoses": ["Septic Shock", "ARDS"],
  "code_status": "Full Code"
}
```

### Using cURL (PowerShell):

```powershell
curl -X POST http://127.0.0.1:8000/v1/summaries `
  -H "Content-Type: application/json" `
  -H "X-Request-ID: test-123" `
  -d @test_sample_request.json
```

Or with inline JSON:

```powershell
$body = @'
{
  "patient": {
    "id": "P12345",
    "name": "John Doe",
    "age": 65,
    "sex": "M"
  },
  "encounter": {
    "id": "E789",
    "admit_time": "2024-01-20T08:00:00Z",
    "icu_day": 3
  },
  "time_window": {
    "start": "2024-01-23T00:00:00Z",
    "end": "2024-01-23T23:59:59Z"
  },
  "flowsheet": [
    {
      "timestamp": "2024-01-23T08:00:00Z",
      "item_name": "Heart Rate",
      "value": "85",
      "unit": "bpm"
    }
  ],
  "meds": [],
  "labs": [],
  "events": [],
  "lines_tubes": [],
  "diagnoses": ["Septic Shock"],
  "code_status": "Full Code"
}
'@

Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/summaries -Method POST -Body $body -ContentType "application/json"
```

### Expected Response:

```json
{
  "note_markdown": "# ICU Daily Summary\n\n## Patient Overview\n...",
  "note_json": {
    "one_liner": "65-year-old male with septic shock, day 3 ICU",
    "overnight_events": ["Central line placed at 02:00"],
    "objective_trends": {},
    "problem_list": [
      {
        "problem": "Septic Shock",
        "assessment": "On norepinephrine 0.15 mcg/kg/min, MAP improving",
        "plan": "Continue vasopressor support, monitor lactate"
      }
    ],
    "lines_tubes": ["Central Line in place", "ETT in place"],
    "prophylaxis": "Not available",
    "nutrition": "Not available",
    "code_status": "Full Code",
    "todo": [],
    "watchouts": []
  },
  "warnings": [],
  "source_counts": {
    "flowsheet": 7,
    "meds": 2,
    "labs": 1,
    "events": 1
  }
}
```

## Minimal Test Example

For a quick test with minimal data:

```json
{
  "patient": {
    "id": "P12345"
  },
  "encounter": {
    "id": "E789"
  },
  "time_window": {
    "start": "2024-01-23T00:00:00Z",
    "end": "2024-01-23T23:59:59Z"
  },
  "flowsheet": [
    {
      "timestamp": "2024-01-23T08:00:00Z",
      "item_name": "Heart Rate",
      "value": "85",
      "unit": "bpm"
    }
  ],
  "meds": [],
  "labs": [],
  "events": [],
  "lines_tubes": []
}
```

## Files Available

- `test_sample_request.json` - Full example with all fields
- `EXAMPLE_REQUEST.json` - Another comprehensive example

Both files are in the project root directory and can be used directly in Postman or curl.
