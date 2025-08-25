# validation_service.py
import subprocess
import json
import re
import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# -----------------------------
# Logging configuration
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ValidationService")

# -----------------------------
# FastAPI App
# -----------------------------
app = FastAPI(title="Field Validation Service")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change to your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Full path to Ollama executable
# -----------------------------
OLLAMA_PATH = r"C:\Users\twitter\AppData\Local\Programs\Ollama\ollama.exe"  # replace with your actual path
MODEL = "gemma3:4b"

# -----------------------------
# Function to run Ollama model
# -----------------------------
def run_ollama(field_name: str, value: str):
    """
    Sends a validation prompt to Ollama Gemma3:4b and parses JSON output.
    """
    prompt = f"""
You are a data validation system.
Validate the following user input field:

Field name: {field_name}
Value: {value}

Rules:
- Respond in strict JSON only.
- If the value is correct/logical, return exactly:
  {{"valid": true}}
- If the value is invalid, return exactly:
  {{"valid": false, "reason": "<short explanation>"}}
- Do not include markdown, extra text, or code fences. Only JSON.
"""

    logger.info(f"Running Ollama model for field '{field_name}'...")

    try:
        process = subprocess.Popen(
            [OLLAMA_PATH, "run", MODEL],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=os.environ.copy()
        )

        output, error = process.communicate(prompt)

        # Log outputs for debugging
        logger.info(f"Ollama stdout length: {len(output)}")
        logger.info(f"Ollama stderr: {error.strip()}")

        # Clean possible ```json fences
        cleaned_output = re.sub(r"^```json\s*|\s*```$", "", output.strip(), flags=re.DOTALL)

        try:
            data = json.loads(cleaned_output)
            logger.info("Validation successful.")
            return data
        except json.JSONDecodeError:
            logger.error("Model did not return valid JSON.")
            return {"raw_output": output, "error": "Model did not return valid JSON"}

    except FileNotFoundError:
        return {"error": f"Ollama executable not found at {OLLAMA_PATH}"}
    except Exception as e:
        return {"error": str(e)}

# -----------------------------
# API Endpoints
# -----------------------------
@app.post("/validate-json/")
async def validate_document_json(request: Request):
    """
    Accepts JSON in the request body:
    {
        "field_name": "email",
        "value": "test@example.com"
    }
    """
    try:
        body = await request.json()
        field_name = body.get("field_name")
        value = body.get("value")

        if not field_name or not value:
            return JSONResponse(
                content={"error": "field_name and value are required"},
                status_code=400
            )

        logger.info(f"Received validation request for field '{field_name}' with value '{value}'")
        result = run_ollama(field_name, value)
        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Error validating JSON document: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/")
def home():
    logger.info("Home route accessed.")
    return {"message": "Validation Service is running!"}
