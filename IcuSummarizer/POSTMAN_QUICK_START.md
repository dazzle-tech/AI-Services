# Postman Quick Start Guide

## Step 1: Start the Server

### Option A: Using PowerShell Script (Easiest)
1. Open PowerShell in the project folder
2. Run:
   ```powershell
   .\start_server.ps1
   ```

### Option B: Manual Start
```powershell
cd C:\Users\User\Desktop\AI-Services\icu-summarizer
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Keep this terminal open!** The server must be running.

---

## Step 2: Import Postman Collection

1. **Open Postman**
2. Click **"Import"** button (top left)
3. Click **"Upload Files"**
4. Navigate to the project folder and select **`postman_collection.json`**
5. Click **"Import"**

You should now see **"ICU Summarizer API"** collection with 4 requests!

---

## Step 3: Test the Endpoints

### ✅ Test 1: Generate Summary (Requires API key)

1. Click on **"Generate Summary"** request
2. The request body is already pre-filled with sample data
3. Click **"Send"**

**Expected Result (Success):**
- Status: `200 OK`
- Response contains:
  ```json
  {
    "note_markdown": "# ICU Daily Summary\n\n...",
    "note_json": {
      "one_liner": "...",
      "problem_list": [...],
      ...
    },
    "warnings": [],
    "source_counts": {...}
  }
  ```

**If you get 500 error:**
- Check that your `.env` file has `OPENAI_API_KEY` set
- Restart the server after adding the API key

---

### ✅ Test 2: Generate Presentation

1. Click on **"Generate Presentation"** request
2. Click **"Send"** (or **"Send and Download"** to save directly)

**Expected Result:**
- Status: `200 OK`
- Response is a binary PPTX file
- To save: Click **"Save Response"** → **"Save to a file"**
- File will be named: `icu_handoff_P12345_...pptx`

---

### ✅ Test 3: Error Cases

#### Test Invalid Time Window
1. Click **"Test Invalid Time Window"**
2. Click **"Send"**
3. **Expected:** `400 Bad Request` with error message

#### Test Missing Required Field
1. Click **"Test Missing Required Field"**
2. Click **"Send"**
3. **Expected:** `422 Unprocessable Entity` with validation errors

---

## Visual Guide: What You Should See

### In Postman:
```
ICU Summarizer API
├── Generate Summary (POST)
├── Generate Presentation (POST)
├── Test Invalid Time Window (POST)
└── Test Missing Required Field (POST)
```

### Response Headers to Check:
- `X-Request-ID` - Should be present in all responses
- `Content-Type` - Should match response type

---

## Troubleshooting

### ❌ "Could not get response"
**Solution:** 
- Check if server is running (Step 1)
- Verify URL is `http://127.0.0.1:8000`

### ❌ "500 Internal Server Error" on summaries/presentations
**Solution:**
- Check `.env` file has `OPENAI_API_KEY`
- Restart server after adding API key
- Run `python test_env.py` to verify .env loading

### ❌ "Connection refused"
**Solution:**
- Server is not running
- Start it using Step 1 instructions

### ❌ Import collection failed
**Solution:**
- Make sure you're importing `postman_collection.json`
- Check file is not corrupted
- Try downloading from the project folder again

---

## Quick Checklist

- [ ] Server is running (see terminal output)
- [ ] Postman collection imported
- [ ] Generate Summary works (returns note_markdown and note_json)
- [ ] Generate Presentation works (downloads PPTX file)
- [ ] Error cases return proper error codes

---

## Tips

1. **Request ID Tracking:** Check response headers - you'll see `X-Request-ID` in every response
2. **Modify Requests:** You can edit the JSON body in Postman to test with different data
3. **Save Responses:** Right-click on response → "Save Response" to save JSON or PPTX files
4. **Collection Variables:** The collection uses `{{base_url}}` - you can change it in collection settings if needed

---

## Next Steps

Once basic testing works:
- Try modifying the request bodies with your own data
- Test with different time windows
- Test with various flowsheet entries
- Check the `warnings` array in responses for data quality issues

Happy testing! 🚀
