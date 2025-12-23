# parsing_service.py
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
logger = logging.getLogger("ParsingService")

# -----------------------------
# FastAPI App
# -----------------------------
app = FastAPI(title="Passport/ID Parsing Service")

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

# -----------------------------
# Function to run Ollama model
# -----------------------------
def run_ollama(extracted_text: str):
    """
    Sends OCR text to Ollama Gemma3:4b and parses JSON output.
    """
    # Basic cleanup: remove empty lines and extra whitespace
    cleaned_text = "\n".join([line.strip() for line in extracted_text.splitlines() if line.strip()])

    prompt = f"""
You are a strict JSON parser. I will give you OCR text from a passport/ID. 
Return ONLY a valid JSON object with these fields:
- Type
- Document Number
- Surname / Family Name
- Given Names
- Nationality
- Date of Birth
- Sex
- Place of Birth

Do NOT include explanations or extra text. If a field is missing, return an empty string.

OCR Text:
{cleaned_text}
"""

    logger.info("Running Ollama model...")

    try:
        process = subprocess.Popen(
            [OLLAMA_PATH, "run", "gemma3:4b"],
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
        logger.info(f"Ollama raw output:\n{output}")

        # Remove ```json fences if present
        cleaned_output = re.sub(r"^```json\s*|\s*```$", "", output.strip(), flags=re.DOTALL)

        try:
            data = json.loads(cleaned_output)
            logger.info("Parsing successful.")
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
@app.post("/parse-json/")
async def parse_document_json(request: Request):
    """
    Accepts JSON in the request body with "text_lines" array.
    Example input:
    {
        "text_lines": ["line1", "line2", ...]
    }
    """
    try:
        body = await request.json()
        if "text_lines" in body:
            extracted_text = "\n".join(body["text_lines"])
        else:
            extracted_text = json.dumps(body)  # fallback if no "text_lines"

        logger.info(f"Received JSON with {len(extracted_text.splitlines())} lines")
        result = run_ollama(extracted_text)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error parsing JSON document: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/")
def home():
    logger.info("Home route accessed.")
    return {"message": "Passport/ID Parsing Service is running!"}
