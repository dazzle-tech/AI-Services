# Postman Testing Guide for ICU Summarizer API

## Prerequisites

1. **Start the server:**
   ```powershell
   cd C:\Users\User\Desktop\AI-Services\icu-summarizer
   $env:PYTHONPATH = (Get-Location).Path
   uvicorn app.main:app --host 127.0.0.1 --port 8013
   ```

2. **Set OpenAI API Key (required for summaries/presentations):**
   ```powershell
   $env:OPENAI_API_KEY = "your-api-key-here"
   ```

## Postman Setup

### 1. Create a New Collection
- Open Postman
- Click "New" → "Collection"
- Name it "ICU Summarizer API"

### 2. Set Collection Variables (Optional)
- Click on the collection → "Variables" tab
- Add variable: `base_url` = `http://127.0.0.1:8013`
- Add variable: `request_id` = `{{$randomUUID}}` (or use a fixed value)

---

## Endpoint 1: Generate Summary

### Request Setup
- **Method:** `POST`
- **URL:** `http://127.0.0.1:8013/v1/summaries`
- **Headers:**
  - `Content-Type: application/json`
  - `X-Request-ID: test-123` (optional, will be auto-generated if not provided)

### Request Body (raw JSON)
Copy the content from `test_sample_request.json` or use this sample:

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
      "timestamp": "2024-01-23T10:00:00Z",
      "item_name": "Mean Arterial Pressure",
      "value": "65",
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

### Expected Response (Success)
```json
{
  "note_markdown": "# ICU Daily Summary\n\n...",
  "note_json": {
    "one_liner": "65-year-old male with septic shock, day 3 ICU",
    "overnight_events": [],
    "objective_trends": {},
    "problem_list": [
      {
        "problem": "Septic Shock",
        "assessment": "On norepinephrine",
        "plan": "Continue vasopressor support"
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
    "flowsheet": 5,
    "meds": 2,
    "labs": 1,
    "events": 1
  }
}
```
- **Status Code:** 200 OK
- **Response Headers:** Includes `X-Request-ID`

### Error Responses

**400 Bad Request** (Invalid time window):
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Time window end must be after start",
    "request_id": "test-123"
  }
}
```

**422 Unprocessable Entity** (Invalid schema):
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

**502 Bad Gateway** (OpenAI error):
```json
{
  "error": {
    "code": "OPENAI_ERROR",
    "message": "OpenAI API error: ...",
    "request_id": "test-123"
  }
}
```

---

## Endpoint 2: Generate Presentation

### Request Setup
- **Method:** `POST`
- **URL:** `http://127.0.0.1:8013/v1/presentations`
- **Headers:**
  - `Content-Type: application/json`
  - `X-Request-ID: test-123` (optional)

### Request Body
Same as the summaries endpoint (use the same JSON from above)

### Expected Response (Success)
- **Status Code:** 200 OK
- **Content-Type:** `application/vnd.openxmlformats-officedocument.presentationml.presentation`
- **Content-Disposition:** `attachment; filename="icu_handoff_P12345_20240123_000000_20240123_235959.pptx"`
- **Body:** Binary PPTX file (download it)

### How to Save the File in Postman
1. Click "Send and Download" button (next to Send)
2. Or click "Send" and then click "Save Response" → "Save to a file"
3. Choose location and save as `.pptx` file

### Error Responses
Same error format as summaries endpoint (400, 422, 502)

---

## Testing Tips

### 1. Test Invalid Time Window
Change the time window to have `end` before `start`:
```json
"time_window": {
  "start": "2024-01-23T23:59:59Z",
  "end": "2024-01-23T00:00:00Z"
}
```
Expected: 400 Bad Request

### 2. Test Missing Required Fields
Remove `patient.id` from the request:
```json
"patient": {
  "name": "John Doe"
  // Missing "id"
}
```
Expected: 422 Unprocessable Entity

### 3. Test Request ID Tracking
- Send a request WITH `X-Request-ID: my-custom-id-123`
- Check response headers - should see `X-Request-ID: my-custom-id-123`
- Send a request WITHOUT `X-Request-ID` header
- Check response headers - should see a generated UUID

### 4. Test Data Outside Time Window
Add flowsheet entries with timestamps outside the time window:
```json
"flowsheet": [
  {
    "timestamp": "2024-01-22T10:00:00Z",  // Before start
    "item_name": "Heart Rate",
    "value": "80"
  }
]
```
Expected: Entry ignored, warning added to response

---

## Quick Test Checklist

- [ ] Summaries endpoint accepts valid payload
- [ ] Summaries endpoint returns 200 with note_markdown and note_json
- [ ] Presentations endpoint returns PPTX file
- [ ] Invalid time window returns 400
- [ ] Missing required fields returns 422
- [ ] Request ID is preserved/generated correctly
- [ ] Error responses include request_id

---

## Import Postman Collection

You can also import the provided `postman_collection.json` file:
1. Open Postman
2. Click "Import"
3. Select `postman_collection.json`
4. All requests will be pre-configured!
