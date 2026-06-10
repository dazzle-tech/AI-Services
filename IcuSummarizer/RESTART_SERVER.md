# How to Restart the Server

## Quick Restart

### If server is running in a terminal:
1. Go to the terminal where server is running
2. Press **Ctrl+C** to stop it
3. Run the start command again (see below)

### If you're not sure if it's running:
1. Check if port 8013 is in use
2. Or just start a new server (it will tell you if port is already in use)

---

## Start Commands

### Option 1: Use the PowerShell Script (Recommended)
```powershell
cd C:\Users\User\Desktop\AI-Services\icu-summarizer
.\start_server.ps1
```

### Option 2: Manual Start
```powershell
cd C:\Users\User\Desktop\AI-Services\icu-summarizer
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --host 127.0.0.1 --port 8013 --reload
```

**Note:** The `--reload` flag means the server will automatically restart when you change code files.

---

## Verify Server is Running

After starting, you should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8013 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

Then test in Postman or browser:
- Docs: http://127.0.0.1:8013/docs
- Generate Summary: POST http://127.0.0.1:8013/v1/summaries

---

## If Port 8013 is Already in Use

You'll see an error like:
```
ERROR:    [Errno 10048] Only one usage of each socket address is permitted
```

**Solution:**
1. Find and stop the process using port 8013:
   ```powershell
   netstat -ano | findstr :8013
   # Note the PID, then:
   taskkill /PID <PID> /F
   ```
2. Or use a different port:
   ```powershell
   uvicorn app.main:app --host 127.0.0.1 --port 8021
   ```
   (Then update Postman collection base_url to use port 8021)
