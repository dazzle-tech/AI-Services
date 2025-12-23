# How to Run and Test the Discharge QA Service

## ✅ Quick Test (Recommended First Step)

Run the simple test script:
```bash
python test_service.py
```

This will:
- Load test data automatically
- Run QA analysis
- Display results
- Save full results to `qa_output.json`

**Expected output:** Score of 90-100 with detailed analysis

---

## 🌐 Run as API Server

### Start the Server
```bash
python src/main.py
```

The server will start on: **http://localhost:8000**

### Test the API

**1. Check if server is running:**
```bash
curl http://localhost:8000/health
```

**2. View API documentation:**
Open in browser: http://localhost:8000/docs

**3. Test the QA endpoint:**

Create a file `test_request.json`:
```json
{
  "discharge_report": "DISCHARGE SUMMARY\nAge: 65\nSex: Male\nDiagnosis: MI",
  "patient_record": {
    "age": 65,
    "sex": "Male",
    "diagnoses": ["MI"]
  },
  "onsite_docs": []
}
```

Then send request:
```bash
curl -X POST "http://localhost:8000/discharge/qa/direct" ^
  -H "Content-Type: application/json" ^
  -d @test_request.json
```

Or use PowerShell:
```powershell
$body = Get-Content test_request.json -Raw
Invoke-RestMethod -Uri "http://localhost:8000/discharge/qa/direct" -Method Post -Body $body -ContentType "application/json"
```

---

## 🧪 Run Unit Tests

```bash
# All tests
pytest tests/

# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# With verbose output
pytest tests/ -v
```

---

## 📋 Test Results

After running `test_service.py`, check:
- **Console output**: Summary of results
- **qa_output.json**: Full detailed results with all errors, inconsistencies, and recommendations

---

## 🔧 Troubleshooting

### "OpenAI API key is required"
- Check that `.env` file exists in project root
- Verify `OPENAI_API_KEY` is set correctly

### "Module not found"
- Run: `pip install -r requirements.txt`
- Make sure you're in the project root directory

### Server won't start
- Check if port 8000 is already in use
- Try: `python src/main.py --port 8001`

### API request fails
- Make sure server is running
- Check request JSON format
- Verify Content-Type header is set

---

## 📊 Understanding Results

- **Overall Score**: 0-100 (higher is better)
- **Errors**: Issues found (completeness, consistency, safety, structure)
- **Missing Items**: Required fields/sections not present
- **Inconsistencies**: Conflicts with patient record or clinical docs
- **Recommended Corrections**: Suggested fixes

---

## 🚀 Next Steps

1. Review `qa_output.json` for detailed analysis
2. Customize quality rules in `docs/quality_rules/`
3. Integrate with your clinical system
4. Add more test cases in `tests/fixtures/`

