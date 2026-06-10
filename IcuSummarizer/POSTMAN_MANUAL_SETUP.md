# Postman Manual Setup (Without Import)

## Step 1: Start the Server

Make sure your server is running:
```powershell
cd C:\Users\User\Desktop\AI-Services\icu-summarizer
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --host 127.0.0.1 --port 8013 --reload
```

---

## Step 2: Create Requests Manually in Postman

### Request 1: Generate Summary

1. **Click "New"** → **"HTTP Request"**
2. **Method:** Select `POST`
3. **URL:** `http://127.0.0.1:8013/v1/summaries`
4. **Headers Tab:**
   - Click "Add Header"
   - Key: `Content-Type`
   - Value: `application/json`
   - (Optional) Add another header:
     - Key: `X-Request-ID`
     - Value: `test-123`
5. **Body Tab:**
   - Select **"raw"**
   - Select **"JSON"** from dropdown
   - Paste this JSON:

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

6. **Click "Save"** → Name it "Generate Summary"
7. **Click "Send"**

**Expected Response:**
- Status: `200 OK`
- Body contains:
  - `note_markdown` (string)
  - `note_json` (object with one_liner, problem_list, etc.)
  - `warnings` (array)
  - `source_counts` (object)

---

### Request 2: Generate Presentation

1. **Click "New"** → **"HTTP Request"**
2. **Method:** Select `POST`
3. **URL:** `http://127.0.0.1:8013/v1/presentations`
4. **Headers Tab:**
   - `Content-Type`: `application/json`
   - (Optional) `X-Request-ID`: `test-123`
5. **Body Tab:**
   - Select **"raw"** → **"JSON"**
   - Use the **same JSON body** as Request 2 (Generate Summary)
6. **Click "Save"** → Name it "Generate Presentation"
7. **Click "Send"** (or "Send and Download")

**Expected Response:**
- Status: `200 OK`
- Body: Binary PPTX file
- To save: Click **"Save Response"** → **"Save to a file"**

---

### Request 3: Test Invalid Time Window (Error Case)

1. **Click "New"** → **"HTTP Request"**
2. **Method:** Select `POST`
3. **URL:** `http://127.0.0.1:8013/v1/summaries`
4. **Headers:**
   - `Content-Type`: `application/json`
5. **Body (raw JSON):**
```json
{
  "patient": {
    "id": "P12345"
  },
  "encounter": {
    "id": "E789"
  },
  "time_window": {
    "start": "2024-01-23T23:59:59Z",
    "end": "2024-01-23T00:00:00Z"
  },
  "flowsheet": [],
  "meds": [],
  "labs": [],
  "events": [],
  "lines_tubes": []
}
```
6. **Click "Save"** → Name it "Test Invalid Time Window"
7. **Click "Send"**

**Expected Response:**
- Status: `400 Bad Request`
- Body: `{"error": {"code": "VALIDATION_ERROR", "message": "...", "request_id": "..."}}`

---

### Request 4: Test Missing Required Field (Error Case)

1. **Click "New"** → **"HTTP Request"**
2. **Method:** Select `POST`
3. **URL:** `http://127.0.0.1:8013/v1/summaries`
4. **Headers:**
   - `Content-Type`: `application/json`
5. **Body (raw JSON):**
```json
{
  "patient": {
    "name": "John Doe"
  },
  "encounter": {
    "id": "E789"
  },
  "time_window": {
    "start": "2024-01-23T00:00:00Z",
    "end": "2024-01-23T23:59:59Z"
  },
  "flowsheet": [],
  "meds": [],
  "labs": [],
  "events": [],
  "lines_tubes": []
}
```
6. **Click "Save"** → Name it "Test Missing Required Field"
7. **Click "Send"**

**Expected Response:**
- Status: `422 Unprocessable Entity`
- Body: Validation error details

---

## Quick Reference: Request Settings

### Generate Summary
- **Method:** POST
- **URL:** `http://127.0.0.1:8013/v1/summaries`
- **Headers:** 
  - `Content-Type: application/json`
  - `X-Request-ID: test-123` (optional)
- **Body:** JSON (see above)

### Generate Presentation
- **Method:** POST
- **URL:** `http://127.0.0.1:8013/v1/presentations`
- **Headers:** Same as Generate Summary
- **Body:** Same JSON as Generate Summary

---

## Tips

1. **Save Requests:** Always save your requests so you can reuse them
2. **Create a Collection:** 
   - Click "New" → "Collection"
   - Name it "ICU Summarizer API"
   - Drag your saved requests into the collection
3. **Copy JSON Body:** You can copy the JSON from `test_sample_request.json` file in the project folder
4. **Check Response Headers:** Look for `X-Request-ID` in response headers
5. **Format JSON:** Postman automatically formats JSON responses for easy reading

---

## Troubleshooting

- **"Could not get response"**: Check if server is running
- **"500 Internal Server Error"**: Check `.env` file has `OPENAI_API_KEY`
- **"Connection refused"**: Server not running - start it first
- **JSON syntax error**: Make sure body is set to "raw" → "JSON" format

---

That's it! You now have all requests set up manually in Postman.
