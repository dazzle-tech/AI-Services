# ErorrCorrectionService.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import T5ForConditionalGeneration, T5Tokenizer
from spellchecker import SpellChecker
import torch
import pandas as pd
import string
import language_tool_python

# ----------------------
# Initialize spell checker and grammar tool
# ----------------------
spell = SpellChecker()
tool = language_tool_python.LanguageTool('en-US')

# ----------------------
# Load T5 model for grammar correction
# ----------------------
t5_model_name = "vennify/t5-base-grammar-correction"
tokenizer = T5Tokenizer.from_pretrained(t5_model_name)
model = T5ForConditionalGeneration.from_pretrained(t5_model_name)


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = model.to(device)
print("Using device:", device)

# ----------------------
# Load CSV files with abbreviations
# ----------------------
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

# ----------------------
# FastAPI App
# ----------------------
app = FastAPI(title="Medical Error Correction Service", version="5.0")

# ----------------------
# Request Model for Single String
# ----------------------
class TextRequest(BaseModel):
    text: str

# ----------------------
# Helper Function
# ----------------------
def correct_spelling_grammar_abbr(sentence: str):
    words = sentence.split()
    processed_words = []

    # Protect medical abbreviations (don’t alter them before model)
    for w in words:
        w_clean = w.lower().strip(string.punctuation)
        if w_clean in medical_abbreviations:
            processed_words.append(w)  # enforce uppercase for clarity
        else:
            processed_words.append(w)

    sentence_preprocessed = " ".join(processed_words)

    # Grammar + spell correction with T5
    input_text = "gec: " + sentence_preprocessed
    inputs = tokenizer.encode(input_text, return_tensors="pt", truncation=True).to(device)
    outputs = model.generate(inputs, max_length=512)
    corrected_sentence = tokenizer.decode(outputs[0], skip_special_tokens=True)

    # Final cleanup with LanguageTool (punctuation, casing, minor grammar fixes)
    matches = tool.check(corrected_sentence)
    corrected_sentence = language_tool_python.utils.correct(corrected_sentence, matches)

    return corrected_sentence

# ----------------------
# API Endpoint: Single String
# ----------------------
@app.post("/correct")
def correct_text(request: TextRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")
    
    corrected_sentence = correct_spelling_grammar_abbr(request.text)
    return {"corrected_text": corrected_sentence}

# ----------------------
# Health Check
# ----------------------
@app.get("/health")
def health_check():
    return {"status": "running"}
