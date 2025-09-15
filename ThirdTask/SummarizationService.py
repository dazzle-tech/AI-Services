from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import json

app = FastAPI(title="Clinical Summary API", version="1.0.0")


# Define input schema
class PatientData(BaseModel):
    Age: int
    Gender: str
    Diagnosis: str
    Symptoms: list[str] = []
    Medications: list[str] = []
    Surgeries: list[str] = []
    Allergies: list[str] = []
    Medical_Warnings: list[str] = []
    Problems: list[str] = []
    Vitals: dict = {}


def generate_summary(patient_data: dict) -> str:
    # Build dynamic patient text
    parts = [f"A {patient_data.get('Age','N/A')}-year-old {patient_data.get('Gender','N/A')} with {patient_data.get('Diagnosis','N/A')}"]

    if patient_data.get("Symptoms"):
        parts.append("Symptoms: " + ", ".join(patient_data["Symptoms"]))
    if patient_data.get("Medications"):
        parts.append("Medications: " + ", ".join(patient_data["Medications"]))
    if patient_data.get("Surgeries"):
        parts.append("Past surgeries: " + ", ".join(patient_data["Surgeries"]))
    if patient_data.get("Allergies"):
        parts.append("Allergies: " + ", ".join(patient_data["Allergies"]))
    if patient_data.get("Medical_Warnings"):
        parts.append("Medical warnings: " + ", ".join(patient_data["Medical_Warnings"]))
    if patient_data.get("Problems"):
        parts.append("Comorbidities: " + ", ".join(patient_data["Problems"]))
    if patient_data.get("Vitals"):
        vitals = patient_data["Vitals"]
        vitals_text = ", ".join([f"{k} {v}" for k, v in vitals.items()])
        parts.append("Vital signs: " + vitals_text)

    patient_text = ". ".join(parts)

    prompt = f"""
Rephrase the following patient data into ONE concise, coherent clinical summary paragraph.
ONLY include the information provided below. 
DO NOT add any extra details, hallucinations, or assumptions.
KEEP all abbreviations exactly as they appear.

Patient data:
{patient_text}

Clinical Summary:
"""

    # Run Ollama model (llama2:13b)
    result = subprocess.run(
        ["ollama", "run", "llama2:13b", prompt],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore"
    )

    clinical_summary = result.stdout.strip()

    # Clean output
    lines = clinical_summary.split('\n')
    cleaned_lines = []
    skip_phrases = [
        "clinical summary:",
        "summary:",
        "here is",
        "okay!"
    ]

    for line in lines:
        line_lower = line.lower().strip()
        if line.strip() and not any(phrase in line_lower for phrase in skip_phrases):
            cleaned_lines.append(line.strip())

    return ' '.join(cleaned_lines).strip()


@app.post("/summarize")
def summarize(patient: PatientData):
    try:
        summary = generate_summary(patient.dict())
        return {"ClinicalSummary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
