# Quick Postman Setup - 5 Steps

## Step 1: Start the Server

Open a terminal and run:
```bash
python src/main.py
```

Wait until you see: `Uvicorn running on http://0.0.0.0:8000`

---

## Step 2: Open Postman

1. Open Postman application
2. Click **New** → **HTTP Request**

---

## Step 3: Configure Request

**Method:** Select **POST**

**URL:** 
```
http://localhost:8000/discharge/qa/direct
```

**Headers Tab:**
- Add: `Content-Type` = `application/json`

**Body Tab:**
1. Select **raw**
2. Select **JSON** (dropdown on right)
3. Copy entire contents of `postman_request_example.json` and paste

---

## Step 4: Send Request

Click the **Send** button

⏱️ Wait 30-60 seconds for response

---

## Step 5: View Results

You'll see a JSON response with:
- `overall_score`: Quality score (0-100)
- `summary`: Text summary
- `errors`: List of errors
- `missing_items`: Missing required fields
- `inconsistencies`: Conflicts found
- `recommended_corrections`: Suggested fixes

---

## Alternative: Import Collection

1. In Postman, click **Import**
2. Select `postman_collection.json`
3. Use pre-configured requests

---

## Troubleshooting

**"Connection refused"**
→ Server not running. Start with `python src/main.py`

**"422 Unprocessable Entity"**
→ Check JSON format. Make sure Content-Type header is set.

**"500 Internal Server Error"**
→ Check `.env` file has `OPENAI_API_KEY` set correctly

