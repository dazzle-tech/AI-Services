# Quick Start: Testing with Postman

## Step 1: Start the Server

Open PowerShell and run:
```powershell
cd C:\Users\User\Desktop\AI-Services\icu-summarizer
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --host 127.0.0.1 --port 8013
```

Keep this terminal open - the server must be running!

## Step 2: Import Postman Collection

1. Open Postman
2. Click **"Import"** button (top left)
3. Click **"Upload Files"**
4. Select `postman_collection.json` from the project folder
5. Click **"Import"**

You should now see "ICU Summarizer API" collection with 4 pre-configured requests!

## Step 3: Test Generate Summary

1. Click on **"Generate Summary"** request
2. Make sure the request body is set to JSON (should be pre-filled)
3. Click **"Send"**

**If you have OpenAI API key set:**
- Status: `200 OK`
- Response contains `note_markdown`, `note_json`, `warnings`, `source_counts`

**If OpenAI API key is NOT set:**
- Status: `500 Internal Server Error`
- This is expected! Set `OPENAI_API_KEY` environment variable to test fully

## Step 4: Test Generate Presentation

1. Click on **"Generate Presentation"** request
2. Click **"Send"** (or **"Send and Download"** to save the file)

**If successful:**
- Status: `200 OK`
- Response is a binary PPTX file
- Click **"Save Response"** → **"Save to a file"** to download

## Step 5: Test Error Cases

### Test Invalid Time Window
1. Click **"Test Invalid Time Window"**
2. Click **"Send"**
3. Expected: `400 Bad Request` with error message

### Test Missing Required Field
1. Click **"Test Missing Required Field"**
2. Click **"Send"**
3. Expected: `422 Unprocessable Entity` with validation errors

## Troubleshooting

### "Could not get response"
- **Check:** Is the server running? (Step 1)
- **Check:** Is the URL correct? Should be `http://127.0.0.1:8013`

### "500 Internal Server Error" on summaries/presentations
- **Check:** Is `OPENAI_API_KEY` set?
- **Solution:** Set it in the terminal before starting server:
  ```powershell
  $env:OPENAI_API_KEY = "sk-your-key-here"
  ```

### "Connection refused"
- Server is not running
- Start it with the command from Step 1

## Tips

- **Request ID:** Each request includes `X-Request-ID` header. Check response headers to see it!
- **Variables:** The collection uses `{{base_url}}` variable - you can change it in collection settings
- **Save Responses:** Right-click on response → "Save Response" to save JSON or PPTX files

## Next Steps

- Modify the request bodies with your own data
- Test with different time windows
- Test with various flowsheet entries
- Check the warnings array in responses

Happy testing! 🚀
