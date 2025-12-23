#!/usr/bin/env python3
"""
medical_rephrase_service.py
Run this service and test with Postman.
"""

import subprocess
import pandas as pd
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ---------- FastAPI app ----------
app = FastAPI(
    title="Medical Note Rephrasing Service",
    description="Rephrases medical notes while keeping abbreviations intact.",
    version="1.0.0"
)

# ---------- Load Abbreviations from CSVs ----------
file_paths = [
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\#-A, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\B, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\C, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\D, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\E-G, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\H, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\I, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\J-L, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\M, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\N-O, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\P, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\Q-R, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\S, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\T, medical abbreviations.csv",
    r"C:\Users\User\Desktop\medical_abbreviations\CSVs\U-Z, medical abbreviations.csv"
]

dfs = [pd.read_csv(path) for path in file_paths]
all_abbreviations = pd.concat(dfs, ignore_index=True)
medical_abbreviations = set(all_abbreviations["Abbreviation/Shorthand"].astype(str).str.lower())

# ---------- Request/Response Models ----------
class NoteRequest(BaseModel):
    original_note: str

class NoteResponse(BaseModel):
    original_note: str
    rephrased_note: str

# ---------- Helper functions ----------
def protect_abbreviations(text: str):
    protected_text = text
    abbr_placeholders = {}

    for abbr in medical_abbreviations:
        # Case-insensitive replacement using regex
        pattern = re.compile(rf"\b{re.escape(abbr)}\b", re.IGNORECASE)
        matches = pattern.findall(protected_text)
        for match in matches:
            placeholder = f"__{match}__"
            abbr_placeholders[placeholder] = match
            protected_text = pattern.sub(placeholder, protected_text, count=1)

    return protected_text, abbr_placeholders

def restore_abbreviations(text: str, abbr_placeholders: dict):
    for placeholder, abbr in abbr_placeholders.items():
        text = text.replace(placeholder, abbr)
    return text

def rephrase_note(original_note: str) -> str:
    # Protect abbreviations
    protected_note, placeholders = protect_abbreviations(original_note)

    # Prompt
    prompt = f"""
    Rephrase the following medical note into a clear, grammatical sentence.
    KEEP all words and abbreviations intact, but you may expand abbreviations if needed.
    Do NOT remove, change, or omit any word.
    Start the sentence naturally with:
        'A [age]-year-old [gender] patient'
    followed by the rest of the patient's conditions and complaints.
    ONLY output the rephrased note, nothing else.
    DO NOT add any extra text, greetings, confirmations, or headings. 
    Start the output immediately with the rephrased note.

    Original Note:
    {protected_note}

    Rephrased Note:
    """

    try:
        result = subprocess.run(
            ["ollama", "run", "llama2:13b", prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=300  # safety timeout
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Ollama request timed out")

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Ollama error: {result.stderr}")

    rephrased_note = result.stdout.strip()

    # Remove polite phrases if model added them
    if rephrased_note.lower().startswith("sure!") or rephrased_note.lower().startswith("here is"):
        rephrased_note = rephrased_note.split("\n\n")[-1].strip()
        first_word_index = min(
            [rephrased_note.find(w) for w in ["Pt", "The", "A", "Patient"] if w in rephrased_note] or [0]
        )
        rephrased_note = rephrased_note[first_word_index:]

    # Restore abbreviations
    rephrased_note = restore_abbreviations(rephrased_note, placeholders)

    return rephrased_note

# ---------- API Endpoint ----------
@app.post("/rephrase", response_model=NoteResponse)
def rephrase_endpoint(request: NoteRequest):
    rephrased = rephrase_note(request.original_note)
    return NoteResponse(original_note=request.original_note, rephrased_note=rephrased)
