#!/usr/bin/env python3
"""
medical_error_service.py
Run the medical error detection as a web service with JSON input/output.
Includes debug logging for abbreviation and misspelling checks.
"""

from flask import Flask, request, jsonify
from pathlib import Path
import json
import re
import pandas as pd
from symspellpy import SymSpell, Verbosity
from wordfreq import zipf_frequency

try:
    import spacy
    HAS_SPACY = True
except ImportError:
    HAS_SPACY = False

# -------------------- Default abbreviation CSV files --------------------
ABBREV_FILE_PATHS = [
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

# -------------------- Load NLP --------------------
def load_nlp():
    if not HAS_SPACY:
        print("[DEBUG] spaCy not installed, skipping NLP")
        return None
    models = ["en_core_sci_sm", "en_core_web_sm"]
    for model in models:
        try:
            nlp_model = spacy.load(model)
            print(f"[DEBUG] Loaded NLP model: {model}")
            return nlp_model
        except Exception:
            continue
    print("[DEBUG] No NLP model loaded")
    return None

# -------------------- Load medical terms --------------------
def load_medical_terms(path: Path):
    if not path.exists():
        print(f"[DEBUG] Medical terms file not found: {path}")
        return set()
    terms = {line.strip().lower() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    print(f"[DEBUG] Loaded {len(terms)} medical terms")
    return terms

# -------------------- Load medical abbreviations using pandas --------------------
def load_medical_abbreviations(file_paths):
    dfs = []
    for path_str in file_paths:
        path = Path(path_str)
        if not path.exists():
            print(f"[DEBUG] Abbreviation file not found: {path_str}")
            continue
        try:
            df = pd.read_csv(path)
            dfs.append(df)
            print(f"[DEBUG] Loaded {len(df)} rows from {path_str}")
        except Exception as e:
            print(f"[DEBUG] Failed to read {path_str}: {e}")
    if not dfs:
        print("[DEBUG] No abbreviation files loaded")
        return {}, pd.DataFrame()
    all_abbreviations = pd.concat(dfs, ignore_index=True)
    print(f"[DEBUG] Total abbreviations loaded: {len(all_abbreviations)}")
    print(all_abbreviations.head())
    # Build abbreviation dictionary
    abbr_dict = dict(zip(all_abbreviations["Abbreviation/Shorthand"].str.upper(), 
                         all_abbreviations["Meaning"]))
    # Test lookup
    print("\nLookup examples:")
    print("N/V →", abbr_dict.get("N/V"))
    print("PT →", abbr_dict.get("PT"))
    return abbr_dict, all_abbreviations

# -------------------- SymSpell --------------------
def init_symspell(med_terms):
    sym = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
    for t in med_terms:
        sym.create_dictionary_entry(t, 50)
    common_words = ["patient","has","with","and","of","for","no","history","presenting","plan",
                    "take","blood","pressure","sugar","pain"]
    for w in common_words:
        sym.create_dictionary_entry(w, 1000)
    print("[DEBUG] SymSpell initialized")
    return sym

# -------------------- Helper functions --------------------
def looks_like_weird_abbrev(token_text, allowlist):
    t = re.sub(r"\.", "", token_text).upper()
    if re.match(r"^(mmHg|HbA1c|eGFR|Na\+|K\+|Cl\-|HCO3|CRP|ESR)$", token_text):
        return False
    is_weird = token_text.isalpha() and token_text.isupper() and 2 <= len(token_text) <= 8 and t not in allowlist
    print(f"[DEBUG] Checking abbreviation '{token_text}': {'UNKNOWN' if is_weird else 'OK'}")
    return is_weird

def is_likely_misspelling(token_text, med_terms, sym, known_entities, zipf_cutoff=2.3):
    t = token_text.strip()
    tl = t.lower()
    if len(t) < 3 or re.search(r"[\d/_+\-]", t):
        return False
    if tl in med_terms or tl in known_entities:
        return False
    if tl.isalpha():
        freq = zipf_frequency(tl, "en")
        if freq < zipf_cutoff:
            sugg = sym.lookup(tl, Verbosity.TOP, max_edit_distance=2)
            if len(sugg) == 0:
                print(f"[DEBUG] Possible misspelling detected: {token_text}")
                return True
    return False

# -------------------- Detect issues --------------------
def detect_issues(text, nlp, med_terms, sym, abbrev_allowlist):
    issues = []
    tokens = []

    if nlp:
        doc = nlp(text)
        known_entities = set(ent.text.lower() for ent in doc.ents)
        for t in doc:
            tokens.append({"text": t.text, "start": t.idx, "end": t.idx+len(t.text),
                           "is_space": t.is_space, "is_punct": t.is_punct})
    else:
        known_entities = set()
        for m in re.finditer(r"\S+|\s+", text):
            seg = m.group(0)
            is_space = seg.isspace()
            tokens.append({"text": seg, "start": m.start(), "end": m.end(),
                           "is_space": is_space, "is_punct": bool(re.fullmatch(r"\W", seg))})

    for tok in tokens:
        if tok["is_space"] or tok["is_punct"]:
            continue
        w = tok["text"]
        if looks_like_weird_abbrev(w, abbrev_allowlist):
            issues.append({"type":"abbreviation","code":"UNKNOWN_ABBREV","token":w,
                           "start":tok["start"],"end":tok["end"],
                           "reason":f"Unrecognized abbreviation '{w}'"})
        if is_likely_misspelling(w, med_terms, sym, known_entities):
            issues.append({"type":"spelling","code":"MISSPELLING","token":w,
                           "start":tok["start"],"end":tok["end"],
                           "reason":f"Possible misspelling or unknown term: '{w}'"})
    print(f"[DEBUG] Total issues detected: {len(issues)}")
    return issues

# -------------------- Flask Service --------------------
app = Flask(__name__)

# Load resources at startup
nlp = load_nlp()
med_terms = load_medical_terms(Path("medical_terms.txt"))
abbr_dict, abbrev_df = load_medical_abbreviations(ABBREV_FILE_PATHS)
sym = init_symspell(med_terms)

# Check HR specifically
if 'HR' in abbr_dict:
    print("[DEBUG] 'HR' found in abbreviation allowlist ✅")
else:
    print("[DEBUG] 'HR' NOT found in abbreviation allowlist ❌")

@app.route("/detect", methods=["POST"])
def detect():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    data = request.get_json()
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No 'text' field provided"}), 400

    print(f"[DEBUG] Received text: {text[:50]}...")  # show first 50 chars
    issues = detect_issues(text, nlp, med_terms, sym, abbr_dict)

    # Add a flag indicating whether there are any issues
    has_errors = len(issues) > 0

    return jsonify({
        "has_errors": has_errors,
        "issues": issues
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
