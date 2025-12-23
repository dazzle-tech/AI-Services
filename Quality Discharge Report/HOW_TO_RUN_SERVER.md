# How to Run the Server

## ✅ Method 1: Using run_server.py (Recommended)

From the project root directory:
```bash
python run_server.py
```

This is the easiest way - no import issues!

---

## ✅ Method 2: Using uvicorn directly

From the project root directory:
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

---

## ✅ Method 3: Using Python module

From the project root directory:
```bash
python -m src.main
```

---

## ❌ Don't Use (Will Cause Import Errors)

```bash
python src/main.py
```

This will fail with import errors because of relative imports.

---

## Verify Server is Running

Once started, you should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

Test it:
- Browser: http://localhost:8000/health
- Should return: `{"status": "healthy"}`

---

## Stop the Server

Press `Ctrl+C` in the terminal where the server is running.

---

## Troubleshooting

### Import Errors
- Make sure you're in the project root directory
- Use `python run_server.py` instead of `python src/main.py`

### Port Already in Use
- Change port: `uvicorn src.main:app --port 8001`
- Or kill the process using port 8000

### Module Not Found
- Install dependencies: `pip install -r requirements.txt`
- Make sure you're in the correct directory

