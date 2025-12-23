# Testing Guide - AI Auto-Population Service V2

## Quick Start

### Option 1: Python Test Script (Recommended)

1. **Start the server** (in one terminal):
   ```bash
   python main.py
   ```
   You should see:
   ```
   INFO:     Uvicorn running on http://0.0.0.0:8000
   ```

2. **Run the test** (in another terminal):
   ```bash
   python test_v2_api.py
   ```

   This will:
   - Test the V2 API with summary + vitals only
   - Validate the response structure
   - Show you the results

### Option 2: Postman

1. **Start the server**:
   ```bash
   python main.py
   ```

2. **Open Postman** and create a new request:
   - **Method**: `POST`
   - **URL**: `http://localhost:8000/api/v1/auto-populate/v2`
   - **Headers**: 
     - `Content-Type`: `application/json`
   - **Body** (select "raw" and "JSON"):
     - Copy the content from `test_request_v2.json`

3. **Click Send**

### Option 3: cURL (Command Line)

1. **Start the server**:
   ```bash
   python main.py
   ```

2. **Run cURL command**:
   ```bash
   curl -X POST "http://localhost:8000/api/v1/auto-populate/v2" \
     -H "Content-Type: application/json" \
     -d @test_request_v2.json
   ```

### Option 4: Import Postman Collection

1. **Open Postman**
2. **Click Import** (top left)
3. **Select**: `AI_Auto_Population.postman_collection.json`
4. **Find**: "Auto-Populate V2 (Doctor Role - Full Request)"
5. **Click Send**

## Test Request File

The file `test_request_v2.json` contains a ready-to-use request:

```json
{
  "request_id": "test_v2_001",
  "task_type": "auto_population",
  "user": {
    "user_id": "doctor_123",
    "role": "doctor",
    "department": "cardiology"
  },
  "languages": {
    "input": "en",
    "output": "en"
  },
  "inputs": {
    "user_text": "Patient is a 65-year-old male presenting with acute chest pain...",
    "onsite": {
      "patient_record_id": "pr_456",
      "is_deidentified": true,
      "documents": [...],
      "patient_data": {...}
    }
  },
  "requested_outputs": {
    "include_summary": true,
    "include_structured_fields": false,
    "include_vitals": true
  }
}
```

## Expected Response

You should receive a response with:
- `outputs.summary` - Clinical summary
- `outputs.structured_fields` - `null` (not requested)
- `outputs.vitals` - Vital signs only
- `quality.uncertainty_flags` - Only vitals-related
- `quality.contradictions` - Only vitals-related
- `trace.source_trace` - Only vitals entries (5 entries)
- `metadata` - Processing information

## Health Check

Test if the server is running:
```bash
curl http://localhost:8000/api/v1/health
```

Or in Postman:
- **Method**: `GET`
- **URL**: `http://localhost:8000/api/v1/health`

Expected response:
```json
{
  "status": "healthy",
  "service": "ai-auto-population"
}
```

## API Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

You can test the API directly from the Swagger UI!

## Troubleshooting

### Server won't start
- Check if port 8000 is already in use
- Verify `.env` file has `OPENAI_API_KEY` set
- Check Python dependencies: `pip install -r requirements.txt`

### 422 Validation Error
- Check JSON syntax in request
- Verify all required fields are present
- Ensure `role` is one of: "doctor", "nurse", "admin"

### 500 Internal Server Error
- Check server logs for details
- Verify OpenAI API key is valid
- Check that model name is correct in `.env`

### Slow Response Time
- Normal: 5-15 seconds for AI processing
- If > 20 seconds, check network/API connection
- Vitals-only requests should be faster (< 10 seconds)

