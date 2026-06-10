# How to Run ICU Summarizer

## Quick Start

Simply run from the project root directory:

```powershell
cd C:\Users\User\Desktop\AI-Services\icu-summarizer
python main.py
```

That's it! The server will start on `http://127.0.0.1:8013`

## Alternative Methods

### Using PowerShell Script
```powershell
.\start_server.ps1
```

### Using Uvicorn Directly
```powershell
uvicorn main:app --reload
```

## What You'll See

When the server starts, you'll see:
```
INFO:     Uvicorn running on http://127.0.0.1:8013 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

## Server URLs

- **API Base**: `http://127.0.0.1:8013`
- **API Documentation**: `http://127.0.0.1:8013/docs`
- **ReDoc**: `http://127.0.0.1:8013/redoc`

## To Stop the Server

Press `Ctrl+C` in the terminal where it's running.

## Notes

- The `--reload` flag (or `reload=True`) enables auto-reload when code changes
- Make sure your `.env` file has `OPENAI_API_KEY` set for full functionality
- The server automatically loads environment variables from `.env` file
