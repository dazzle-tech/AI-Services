from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Dict
import requests
import json
import re

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "mistral" 

app = FastAPI(title="mistral ai model")

class PatientVitals(BaseModel):
    Temperature: Optional[str] = None
    Heart_Rate: Optional[str] = None
    Respiratory_Rate: Optional[str] = None
    Oxygen_Saturation: Optional[str] = None
    Blood_Pressure: Optional[str] = None

class LaboratoryResults(BaseModel):
    HbA1c: Optional[str] = None
    Glucose: Optional[str] = None

class PatientRecord(BaseModel):
    Age: Optional[int] = None
    Gender: Optional[str] = None
    Diagnosis: Optional[str] = None
    Symptoms: Optional[List[str]] = None
    Medications: Optional[List[str]] = None
    Surgeries: Optional[List[str]] = None
    Allergies: Optional[List[str]] = None
    Medical_Warnings: Optional[List[str]] = None
    Problems: Optional[List[str]] = None
    Vitals: Optional[PatientVitals] = None
    Pregnancy: Optional[bool] = None
    Laboratory_Results: Optional[LaboratoryResults] = None
    Pain_Score: Optional[int] = None
    Fluid_Balance: Optional[str] = None
    Nutrition_State: Optional[str] = None
    ECG: Optional[str] = None
    Fall_Risk: Optional[str] = None
    Vaccines: Optional[List[str]] = None
    Coma_Scale: Optional[str] = None
    Pressure_Ulcer: Optional[str] = None

def normalize_input(record: PatientRecord) -> str:
    """Flatten patient data into readable text for the AI."""
    return json.dumps(record.dict(), indent=2)

def extract_json(text: str) -> dict:
    """Extract valid JSON from model output, fallback if needed."""
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return {"contradictions": [], "missing_data": []}

# def ai_based_check(text: str) -> dict:
#     """Send patient case to model and return structured analysis."""
#     prompt = f"""
# You are a medical consistency checker.
# Analyze the patient record and return ONLY JSON.

# JSON format:
# {{
#   "contradictions": ["..."],
#   "missing_data": ["..."]
# }}

# Rules:
# - "contradictions": impossible or inconsistent facts (e.g. male pregnancy, HR = 500 bpm).
# - "missing_data": fields REQUIRED for this patient’s case (based on diagnosis, symptoms, or risks) that are null or missing.
# - Do not list every null field, only those medically required.
# - Always output valid JSON. No text outside JSON.

# Clinical dependency rules:
# - If Diagnosis includes "Diabetes" → Laboratory_Results and Nutrition_State required.
# - If Symptoms include "chest pain" OR "angina" OR "shortness of breath" → ECG required.
# - If Fall_Risk = "High" → Pressure_Ulcer and Coma_Scale required.
# - If patient has Obesity or Hypertension → Fluid_Balance recommended.
# - If Pregnancy = true → Nutrition_State and Laboratory_Results required.

# Patient record:
# {text}

# Output:
# """
#     try:
#         response = requests.post(
#             OLLAMA_URL,
#             json={"model": MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0}},
#             timeout=120
#         )
#         result = response.json()
#         raw = result.get("response", "").strip()
#         parsed = extract_json(raw)
#         return parsed
#     except Exception as e:
#         return {"contradictions": [f"Error: {str(e)}"], "missing_data": []}

# def ai_based_check(text: str) -> dict:
#     """Send patient case to model and return structured analysis."""
#     prompt = f"""
# You are a medical consistency checker.
# Study the patient record carefully.

# Return JSON ONLY in this format:
# {{
#   "contradictions": ["..."],
#   "missing_data": ["..."]
# }}

# Guidelines:
# - "contradictions": include ANY logically impossible, biologically unrealistic, or medically unrecognized facts.
#   Examples:
#     - Male pregnancy.
#     - Age < 0 or > 130.
#     - Heart rate 5000 bpm.
#     - Diagnosis that is not a real medical condition.
#     - Symptom that is not a real medical symptom.
#     - Treatments/medications that are not valid.
# - If unsure whether something is valid in medicine, list it under contradictions.
# - "missing_data": fields REQUIRED for this patient’s case (based on diagnosis, symptoms, or risks) that are null or missing.
#   Examples:
#     - Diabetes → Laboratory_Results, Nutrition_State.
#     - Chest pain → ECG.
#     - Fall_Risk = High → Pressure_Ulcer, Coma_Scale.
# - Do not list every null field, only those clinically required.
# - Always output valid JSON. No text outside JSON.
# - Only add fields to "missing_data" if they are medically required given the specific case context.
# - Do not add fields that are unrelated to the patient’s diagnosis, symptoms, or risks.
# - Do not include fields in "missing_data" if they already have a value.
# - Do not include fields in "missing_data" unless they are both (a) clinically required and (b) null or missing.

# Patient record:
# {text}

# Output:
# """
#     try:
#         response = requests.post(
#             OLLAMA_URL,
#             json={"model": MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0}},
#             timeout=120
#         )
#         result = response.json()
#         raw = result.get("response", "").strip()
#         parsed = extract_json(raw)
#         return parsed
#     except Exception as e:
#         return {"contradictions": [f"Error: {str(e)}"], "missing_data": []}

def ai_based_check(text: str) -> dict:
    """Send patient case to model and return structured analysis."""
    prompt = f"""
You are a medical consistency checker.
Your job is to study the ENTIRE patient case holistically,
like a doctor reviewing a chart.

Return JSON ONLY in this format:
{{
  "contradictions": ["..."],
  "missing_data": ["..."]
}}

Guidelines:

- "contradictions": list only biologically IMPOSSIBLE or logically INCONSISTENT facts.  
  Examples:
    - Male pregnancy.
    - Age < 0 or > 130.
    - Oxygen saturation > 100%.
    - Heart rate > 300 bpm in any context.
    - Pregnancy at age 5 (not biologically possible).
    - Diagnoses or symptoms that are not medically recognized.

- IMPORTANT: Do NOT flag values as contradictions if they are abnormal but still
  consistent with the given diagnosis or symptoms.
  Examples:
    - HR 160, BP 75/40, SpO₂ 89% → acceptable in Severe Sepsis.
    - SpO₂ 88% → consistent with advanced COPD.
    - Pain score 10 → valid, even if extreme.

- "missing_data": include only information that is CLINICALLY REQUIRED for this case
  and is null or missing.
  Examples:
    - Diabetes → Laboratory_Results, Nutrition_State.
    - Chest pain/angina/shortness of breath → ECG.
    - Fall_Risk = High → Pressure_Ulcer, Coma_Scale.
    - Pregnancy = true → Laboratory_Results, Nutrition_State.
    - Severe conditions (sepsis, hemorrhage, trauma, shock) → Laboratory_Results, Nutrition_State, Fluid_Balance.


- Do not list every null field, only those clinically relevant.
- Do not include fields already filled.
- If data is unusual but medically plausible, do NOT list it under contradictions.

Patient record:
{text}

Output (only JSON):
"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0}},
            timeout=120
        )
        result = response.json()
        raw = result.get("response", "").strip()
        parsed = extract_json(raw)
        return parsed
    except Exception as e:
        return {"contradictions": [f"Error: {str(e)}"], "missing_data": []}

def is_missing(value):
    return value is None or value == "" or value == {} or value == []

def rule_based_dependencies(record: PatientRecord) -> list[str]:
    missing = []

    data = record.dict()

    if data.get("Diagnosis") and "diabetes" in data["Diagnosis"].lower():
        if not data.get("Laboratory_Results"):
            missing.append("Laboratory_Results")
        if not data.get("Nutrition_State"):
            missing.append("Nutrition_State")

    symptoms = [re.sub(r"\s+", " ", s.lower().strip()) for s in (data.get("Symptoms") or [])]
    if any(term in symptoms for term in ["chest pain", "angina", "shortness of breath"]):
        if not data.get("ECG"):
           missing.append("ECG")

    if data.get("Fall_Risk") and str(data["Fall_Risk"]).lower() == "high":
        if is_missing(data.get("Pressure_Ulcer")):
           missing.append("Pressure_Ulcer")
        if is_missing(data.get("Coma_Scale")):
           missing.append("Coma_Scale")

    problems = [re.sub(r"\s+", " ", s.lower().strip()) for s in (data.get("Problems") or [])]
    if any(term in problems for term in ["obesity", "hypertension"]):
        if not data.get("Fluid_Balance"):
            missing.append("Fluid_Balance")

    return list(set(missing)) 

# def sanity_checks(record: PatientRecord, ai_contradictions: list[str]) -> list[str]:
#     contradictions = []
#     data = record.dict()
#     vitals = data.get("Vitals") or {}

#     if data.get("Age") is not None:
#         if data["Age"] < 0 or data["Age"] > 130:
#             contradictions.append(f"Unrealistic age: {data['Age']}")

#     if data.get("Gender") and data.get("Pregnancy"):
#         if str(data["Gender"]).lower() == "male" and data["Pregnancy"] is True:
#             contradictions.append("A male cannot be pregnant")

#     if data.get("Pregnancy") and data.get("Age") is not None:
#         if data["Age"] < 12:
#            contradictions.append(f"Pregnancy at age {data['Age']} is biologically impossible")

#     try:
#         t = float(str(vitals.get("Temperature", "0")).replace("°C", "").strip())
#         if t < 25 or t > 45:
#             contradictions.append(f"Unrealistic temperature: {t}°C")
#     except Exception:
#         pass

#     try:
#         hr = int("".join([c for c in str(vitals.get("Heart_Rate", "")) if c.isdigit()]))
#         if hr < 20 or hr > 300:
#             contradictions.append(f"Unrealistic heart rate: {hr} bpm")
#     except Exception:
#         pass

#     try:
#         rr = int("".join([c for c in str(vitals.get("Respiratory_Rate", "")) if c.isdigit()]))
#         if rr < 5 or rr > 60:
#             contradictions.append(f"Unrealistic respiratory rate: {rr}/min")
#     except Exception:
#         pass

#     try:
#         spo2 = int("".join([c for c in str(vitals.get("Oxygen_Saturation", "")) if c.isdigit()]))
#         if spo2 < 50 or spo2 > 100:
#             contradictions.append(f"Unrealistic oxygen saturation: {spo2}%")
#     except Exception:
#         pass

#     try:
#         bp = str(vitals.get("Blood_Pressure", ""))
#         parts = bp.replace("mmHg", "").split("/")
#         if len(parts) == 2:
#             sys, dia = int(parts[0]), int(parts[1])
#             if sys < 50 or sys > 300 or dia < 30 or dia > 200:
#                 contradictions.append(f"Unrealistic blood pressure: {sys}/{dia} mmHg")
#     except Exception:
#         pass

#     if data.get("Pain_Score") is not None:
#         if data["Pain_Score"] < 0 or data["Pain_Score"] > 10:
#             contradictions.append(f"Unrealistic pain score: {data['Pain_Score']}")

#     if data.get("Coma_Scale") is not None:
#         try:
#             coma = int(str(data["Coma_Scale"]))
#             if coma < 3 or coma > 15:
#                 contradictions.append(f"Unrealistic coma scale: {coma}")
#         except Exception:
#             contradictions.append(f"Invalid coma scale format: {data['Coma_Scale']}")

#     final = []
#     for c in contradictions:
#         if all(c.lower() not in a.lower() for a in ai_contradictions):
#             final.append(c)

#     return final

def sanity_checks(record: PatientRecord, ai_contradictions: list[str]) -> list[str]:
    contradictions = []
    data = record.dict()
    vitals = data.get("Vitals") or {}

    if data.get("Age") is not None:
        if data["Age"] < 0 or data["Age"] > 130:
            contradictions.append(f"Unrealistic age: {data['Age']}")

    if data.get("Gender") and data.get("Pregnancy"):
        if str(data["Gender"]).lower() == "male" and data["Pregnancy"] is True:
            contradictions.append("A male cannot be pregnant")

    try:
        t = float(str(vitals.get("Temperature", "0")).replace("°C", "").strip())
        if t < 25 or t > 45:
            contradictions.append(f"Unrealistic temperature: {t}°C")
    except Exception:
        pass

    try:
        hr = int("".join([c for c in str(vitals.get("Heart_Rate", "")) if c.isdigit()]))
        if hr < 20 or hr > 300:
            contradictions.append(f"Unrealistic heart rate: {hr} bpm")
    except Exception:
        pass

    try:
        spo2 = int("".join([c for c in str(vitals.get("Oxygen_Saturation", "")) if c.isdigit()]))
        if spo2 < 50 or spo2 > 100:
            contradictions.append(f"Unrealistic oxygen saturation: {spo2}%")
    except Exception:
        pass

    if data.get("Pain_Score") is not None:
        if data["Pain_Score"] < 0 or data["Pain_Score"] > 10:
            contradictions.append(f"Unrealistic pain score: {data['Pain_Score']}")

    if data.get("Coma_Scale") is not None:
        try:
            coma = int(str(data["Coma_Scale"]))
            if coma < 3 or coma > 15:
                contradictions.append(f"Unrealistic coma scale: {coma}")
        except Exception:
            contradictions.append(f"Invalid coma scale format: {data['Coma_Scale']}")

    final = [c for c in contradictions if all(c.lower() not in a.lower() for a in ai_contradictions)]
    return final

@app.post("/check")
def check_record(record: PatientRecord):
    text = normalize_input(record)
    ai_result = ai_based_check(text)

    ai_contradictions = ai_result.get("contradictions", [])
    ai_missing = ai_result.get("missing_data", [])

    extra_contradictions = sanity_checks(record, ai_contradictions)
    rule_missing = rule_based_dependencies(record)

    contradictions = list(set(ai_contradictions + extra_contradictions))

    missing_data = list(set(ai_missing + rule_missing))
    # missing_data = list(set(rule_missing))  

    missing_data = [f for f in missing_data if record.dict().get(f) in (None, "", [], {})]

    is_consistent = len(contradictions) == 0 and len(missing_data) == 0

    return {
        "input": record.dict(),
        "ai_analysis": {
            "contradictions": contradictions,
            "missing_data": missing_data
        },
        "consistent": is_consistent,
        "model_used": MODEL
    }
