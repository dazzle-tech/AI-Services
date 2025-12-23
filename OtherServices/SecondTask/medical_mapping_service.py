#!/usr/bin/env python3
"""
medical_mapping_service.py
Run this service and test with Postman.
"""

import subprocess
import json
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ---------- FastAPI app ----------
app = FastAPI(
    title="Medical Note Mapping Service",
    description="Extracts structured medical data from clinical notes while preserving abbreviations and expanding shorthand medication orders.",
    version="1.1.0"
)

# ---------- Request/Response Models ----------
class NoteRequest(BaseModel):
    clinical_note: str

class StructuredResponse(BaseModel):
    clinical_note: str
    structured_data: dict

# ---------- Target fields ----------
fields = [
    "Gender/Sex at Birth",
    "Age",
    "Chief Complaint",
    "Chronic Illness/PMH",
    "Systolic BP",
    "Diastolic BP",
    "Heart Rate/Pulse",
    "Temp",
    "ECG Interpretation",
    "Medication Order",
    "Fluid Order",
    "Procedure Request"
]

# ---------- Helper functions ----------
def extract_numeric(value):
    match = re.search(r"\d+\.?\d*", str(value))
    return float(match.group()) if match else None

def pluralize(value: str, singular: str, plural: str) -> str:
    """Return singular if value == 1 else plural."""
    return singular if value == "1" else plural

def expand_shorthand(med: str) -> str:
    """
    Expand shorthand if present (nXnXn or nxnxn) with proper singular/plural.
    Example: "Metoprolol 50mg 1x2x7" -> "Metoprolol 50mg, 1 unit, 2 times daily, 7 days"
    """
    match = re.search(r"(\d+)[xX](\d+)[xX](\d+)", med)  # match both x and X
    if match:
        qty, freq, days = match.groups()
        drug_part = re.sub(r"\s*\d+[xX]\d+[xX]\d+", "", med).strip()
        unit_word = pluralize(qty, "unit", "units")
        time_word = pluralize(freq, "time", "times")
        day_word = pluralize(days, "day", "days")
        return f"{drug_part}, {qty} {unit_word}, {freq} {time_word} daily, {days} {day_word}"
    return med

def map_note_to_structured(note: str) -> dict:
    prompt = f"""
Extract the following structured medical data from the clinical note below.
Keep ALL abbreviations exactly as they appear in the note.
Do NOT change or expand abbreviations.
Output ONLY JSON with the following fields: {fields}

Clinical Note:
{note}

JSON Output:
"""
    try:
        result = subprocess.run(
            ["ollama", "run", "llama2:13b", prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=300
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Ollama request timed out")

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Ollama error: {result.stderr}")

    raw_output = result.stdout.strip()

    # Extract JSON
    json_match = re.search(r"\{.*\}", raw_output, re.DOTALL)
    if not json_match:
        raise HTTPException(status_code=500, detail="No JSON found in model output")

    try:
        structured_data = json.loads(json_match.group())
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse JSON from model output")

    # ---------- Standardize numeric fields ----------
    try:
        if "Age" in structured_data:
            structured_data["Age"] = int(extract_numeric(structured_data.get("Age")))
        if "Systolic BP" in structured_data:
            structured_data["Systolic BP"] = int(extract_numeric(structured_data.get("Systolic BP")))
        if "Diastolic BP" in structured_data:
            structured_data["Diastolic BP"] = int(extract_numeric(structured_data.get("Diastolic BP")))
        if "Heart Rate/Pulse" in structured_data:
            structured_data["Heart Rate/Pulse"] = int(extract_numeric(structured_data.get("Heart Rate/Pulse")))
        if "Temp" in structured_data:
            structured_data["Temp"] = extract_numeric(structured_data.get("Temp"))
    except Exception as e:
        print(f"[DEBUG] Numeric conversion failed: {e}")

    # ---------- Expand shorthand in Medication Orders ----------
        # ---------- Expand shorthand in Medication Orders ----------
    if "Medication Order" in structured_data:
        meds = structured_data["Medication Order"]

        # If it's a single string, wrap in a list
        if isinstance(meds, str):
            meds = [meds]

        if isinstance(meds, list):
            expanded_meds = []
            print("\n[DEBUG] Medication Orders before expansion:", meds)
            for med in meds:
                expanded = expand_shorthand(med)
                expanded_meds.append(expanded)
                print(f"[DEBUG] {med}  -->  {expanded}")
            structured_data["Medication Order"] = expanded_meds
            print("[DEBUG] Final Expanded Medications:", structured_data["Medication Order"])
        else:
            print(f"[DEBUG] Medication Order is not list or string: {meds}")
    else:
        print("[DEBUG] No Medication Orders found.")

    return structured_data

# ---------- API Endpoint ----------
@app.post("/map_note", response_model=StructuredResponse)
def map_note_endpoint(request: NoteRequest):
    structured_data = map_note_to_structured(request.clinical_note)
    return StructuredResponse(clinical_note=request.clinical_note, structured_data=structured_data)
