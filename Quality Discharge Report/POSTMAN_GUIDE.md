# Testing in Postman - Step by Step Guide

## Prerequisites

1. **Start the API Server** (in a separate terminal):
   ```bash
   python src/main.py
   ```
   The server should be running on `http://localhost:8000`

2. **Install Postman** (if not already installed)
   - Download from: https://www.postman.com/downloads/

---

## Method 1: Import Postman Collection (Easiest)

### Step 1: Import Collection
1. Open Postman
2. Click **Import** button (top left)
3. Select `postman_collection.json` file
4. Click **Import**

### Step 2: Test Health Check
1. In Postman, find **"Health Check"** request
2. Click **Send**
3. Should return: `{"status": "healthy"}`

### Step 3: Test QA Endpoint
1. Find **"Direct QA - Full Example"** request
2. Click **Send**
3. Wait 30-60 seconds for response
4. Review the JSON response with QA results

---

## Method 2: Manual Setup in Postman

### Step 1: Create New Request

1. Open Postman
2. Click **New** → **HTTP Request**
3. Name it: "Discharge QA - Direct"

### Step 2: Configure Request

**Method:**
- Select **POST** from dropdown

**URL:**
```
http://localhost:8000/discharge/qa/direct
```

**Headers:**
1. Go to **Headers** tab
2. Add header:
   - Key: `Content-Type`
   - Value: `application/json`

**Body:**
1. Go to **Body** tab
2. Select **raw**
3. Select **JSON** from dropdown (right side)
4. Paste this JSON:

```json
{
  "discharge_report": "DISCHARGE SUMMARY\n\nPatient Information:\nAge: 65\nSex: Male\nAdmission Date: 2024-01-15\nDischarge Date: 2024-01-18\n\nChief Complaint:\nChest pain and shortness of breath\n\nDiagnoses:\nPrimary: Acute ST-elevation myocardial infarction\n\nMedications on Discharge:\n- Aspirin 81mg PO daily\n- Clopidogrel 75mg PO daily\n\nAllergies:\nNo known drug allergies\n\nDischarge Disposition:\nHome",
  "patient_record": {
    "age": 65,
    "sex": "Male",
    "admission_date": "2024-01-15",
    "discharge_date": "2024-01-18",
    "diagnoses": [
      "Acute ST-elevation myocardial infarction"
    ],
    "medications": [
      {
        "name": "Aspirin",
        "dose": "81mg",
        "frequency": "daily"
      }
    ],
    "allergies": []
  },
  "onsite_docs": [
    {
      "doc_id": "DOC-001",
      "doc_type": "progress_note",
      "timestamp": "2024-01-15T10:00:00Z",
      "department": "Cardiology",
      "content": "Patient stable. No complications.",
      "is_deidentified": true
    }
  ],
  "report_template": null,
  "quality_rules": null
}
```

### Step 3: Send Request

1. Click **Send** button
2. Wait for response (30-60 seconds)
3. View results in **Response** section

---

## Understanding the Response

The response will be a JSON object with:

```json
{
  "qa_method": "direct_qa",
  "overall_score": 93,
  "summary": "...",
  "parsed_report": {...},
  "errors": [...],
  "missing_items": [...],
  "inconsistencies": [...],
  "recommended_corrections": [...]
}
```

### Key Fields:
- **overall_score**: Quality score (0-100)
- **summary**: Text summary of findings
- **errors**: List of errors found
- **missing_items**: Required items not present
- **inconsistencies**: Conflicts with source data
- **recommended_corrections**: Suggested fixes

---

## Quick Test Requests

### Minimal Request (Just Required Fields)
```json
{
  "discharge_report": "DISCHARGE SUMMARY\nAge: 65\nDiagnosis: MI",
  "patient_record": {
    "age": 65,
    "sex": "Male",
    "diagnoses": ["MI"]
  },
  "onsite_docs": []
}
```

### Full Request (All Fields)
Use the example from `postman_collection.json` or the full example above.

---

## Troubleshooting

### "Connection refused" or "Could not get response"
- **Solution**: Make sure the server is running
  ```bash
  python src/main.py
  ```
- Check that it says: `Uvicorn running on http://0.0.0.0:8000`

### "422 Unprocessable Entity"
- **Solution**: Check your JSON format
- Make sure Content-Type header is set to `application/json`
- Validate JSON syntax (no trailing commas, proper quotes)

### "500 Internal Server Error"
- **Solution**: Check server logs for error details
- Verify `.env` file has `OPENAI_API_KEY` set
- Check OpenAI API key is valid

### Response takes too long
- **Normal**: First request can take 30-60 seconds
- The AI analysis takes time to process
- Subsequent requests may be faster

---

## Tips

1. **Save Request**: Click **Save** to save your request for later
2. **Create Collection**: Organize requests in a collection
3. **Environment Variables**: Use variables for `localhost:8000` to easily switch between dev/prod
4. **Pre-request Scripts**: Can add scripts to load data from files
5. **Tests**: Add tests to validate response structure

---

## Example Environment Variables

Create a Postman Environment:
- Variable: `base_url`
- Value: `http://localhost:8000`

Then use in URL: `{{base_url}}/discharge/qa/direct`

---

## Next Steps

1. Test with your own discharge reports
2. Customize request body with real data
3. Save successful requests as examples
4. Create tests to validate response structure
5. Set up environment for different servers (dev/staging/prod)

