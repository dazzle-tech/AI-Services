from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import subprocess
import json

app = FastAPI(title="Medical Consistency Checker API")

# -------------------------------
# Rule-based checks (raw flags)
# -------------------------------
def rule_based_checks(record):
    issues = []

    # Pregnancy check
    if record.get("Pregnancy") and str(record["Pregnancy"]).lower() == "pregnant":
        if record.get("Gender", "").lower() == "male":
            issues.append({
                "field": "Pregnancy",
                "issue": "Pregnancy marked but patient is male",
                "explanation": "Pregnancy is only possible for biological females."
            })

    # Pain score check (0-10)
    if "Pain Score" in record:
        score = record["Pain Score"]
        if not isinstance(score, (int, float)) or not (0 <= score <= 10):
            issues.append({
                "field": "Pain Score",
                "issue": "Out of range",
                "explanation": "Pain score must be between 0 and 10."
            })

    # Coma Scale check (0-15)
    if "Coma Scale" in record:
        try:
            score = int(str(record["Coma Scale"]).split("/")[0])
            if not (0 <= score <= 15):
                issues.append({
                    "field": "Coma Scale",
                    "issue": "Out of range",
                    "explanation": "Glasgow Coma Scale ranges from 0 to 15."
                })
        except:
            pass

    # Vitals sanity checks
    if "Vitals" in record:
        vitals = record["Vitals"]

        if "Heart Rate" in vitals:
            try:
                hr = int(vitals["Heart Rate"].split()[0])
                if hr < 40 or hr > 180:
                    issues.append({
                        "field": "Vitals",
                        "issue": "Abnormal heart rate",
                        "explanation": f"Heart rate {hr} bpm is outside adult range (40-180)."
                    })
            except:
                pass

        if "Temperature" in vitals:
            try:
                temp = float(vitals["Temperature"].replace("°C",""))
                if temp < 35 or temp > 42:
                    issues.append({
                        "field": "Vitals",
                        "issue": "Abnormal temperature",
                        "explanation": f"Temperature {temp}°C is outside plausible human range (35-42)."
                    })
            except:
                pass

    # Laboratory Results sanity checks
    if "Laboratory Results" in record:
        labs = record["Laboratory Results"]

        if "HbA1c" in labs:
            try:
                hba1c = float(labs["HbA1c"].replace("%",""))
                if hba1c < 3.5 or hba1c > 20:
                    issues.append({
                        "field": "Laboratory Results",
                        "issue": "Impossible HbA1c value",
                        "explanation": f"HbA1c {hba1c}% is outside physiologically possible range (3.5–20).",
                        "force_verdict": "True Inconsistency"
                    })
            except:
                pass

        if "Cholesterol" in labs:
            try:
                chol = int(labs["Cholesterol"].split()[0])
                if chol < 50 or chol > 600:
                    issues.append({
                        "field": "Laboratory Results",
                        "issue": "Implausible cholesterol value",
                        "explanation": f"Cholesterol {chol} mg/dL is outside plausible range (50–600).",
                        "force_verdict": "True Inconsistency"
                    })
            except:
                pass

    return issues


# -------------------------------
# Convert patient dict to text
# -------------------------------
def build_patient_text(patient_data):
    parts = [f"A {patient_data.get('Age','N/A')}-year-old {patient_data.get('Gender','N/A')} with {patient_data.get('Diagnosis','N/A')}"]

    if patient_data.get("Symptoms"):
        parts.append("Symptoms: " + ", ".join(patient_data["Symptoms"]))
    if patient_data.get("Medications"):
        parts.append("Medications: " + ", ".join(patient_data["Medications"]))
    if patient_data.get("Surgeries"):
        parts.append("Past surgeries: " + ", ".join(patient_data["Surgeries"]))
    if patient_data.get("Allergies"):
        parts.append("Allergies: " + ", ".join(patient_data["Allergies"]))
    if patient_data.get("Medical Warnings"):
        parts.append("Medical warnings: " + ", ".join(patient_data["Medical Warnings"]))
    if patient_data.get("Problems"):
        parts.append("Comorbidities: " + ", ".join(patient_data["Problems"]))
    if patient_data.get("Vitals"):
        vitals_text = ", ".join([f"{k} {v}" for k,v in patient_data["Vitals"].items()])
        parts.append("Vital signs: " + vitals_text)

    parts.append("Pregnancy status: " + str(patient_data.get("Pregnancy", "N/A")))
    labs = patient_data.get("Laboratory Results", {})
    labs_text = ", ".join([f"{k}: {v}" for k,v in labs.items()]) if labs else "None"
    parts.append("Laboratory results: " + labs_text)

    parts.append(f"Pain score: {patient_data.get('Pain Score', 'N/A')}")
    parts.append(f"Fluid balance: {patient_data.get('Fluid Balance', 'N/A')}")
    parts.append(f"Nutrition state: {patient_data.get('Nutrition State', 'N/A')}")
    parts.append(f"ECG: {patient_data.get('ECG', 'N/A')}")
    parts.append(f"Fall risk: {patient_data.get('Fall Risk', 'N/A')}")
    parts.append("Vaccines: " + ", ".join(patient_data.get("Vaccines", ["None"])))
    parts.append(f"Coma scale: {patient_data.get('Coma Scale', 'N/A')}")
    parts.append(f"Pressure ulcer: {patient_data.get('Pressure Ulcer', 'N/A')}")

    return ". ".join(parts)


# -------------------------------
# Ask Med42 to contextualize rule flags
# -------------------------------
def llm_contextualize_flags(patient_data, raw_flags):
    # Skip LLM if forced verdict is present
    if any("force_verdict" in issue for issue in raw_flags):
        contextualized = []
        for issue in raw_flags:
            if "force_verdict" in issue:
                contextualized.append({
                    "field": issue["field"],
                    "issue": issue["issue"],
                    "verdict": issue["force_verdict"],
                    "explanation": issue["explanation"]
                })
            else:
                contextualized.append(issue)
        return contextualized

    patient_text = build_patient_text(patient_data)

    prompt = f"""
You are a medical consistency auditor. A rule-based system flagged the following possible issues:

{json.dumps(raw_flags, indent=2)}

Patient data:
{patient_text}

Instructions:
1. Review the flagged issues in the context of the patient's comorbidities, medications, and conditions.
2. For each flagged issue, decide whether it is a TRUE inconsistency or EXPLAINABLE given the patient’s context.
3. Output strictly in JSON array format with:
   - field
   - issue
   - verdict ("True Inconsistency" or "Explained by context")
   - explanation
"""

    result = subprocess.run(
        ["ollama", "run", "thewindmom/llama3-med42-8b", prompt],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore"
    )

    raw_output = result.stdout.strip()

    try:
        return json.loads(raw_output)
    except:
        start = raw_output.find("[")
        end = raw_output.rfind("]") + 1
        try:
            return json.loads(raw_output[start:end])
        except:
            return [{"field": "System", "issue": "Parsing failed", "verdict": "Error", "explanation": raw_output}]


# -------------------------------
# Hybrid consistency checker
# -------------------------------
def hybrid_consistency_check(patient_data):
    raw_flags = rule_based_checks(patient_data)
    contextualized = llm_contextualize_flags(patient_data, raw_flags)

    # Compute overall flag
    verdicts = [issue.get("verdict") for issue in contextualized]
    if "True Inconsistency" in verdicts:
        overall_flag = "Inconsistent"
    elif "Explained by context" in verdicts:
        overall_flag = "Contextually Consistent"
    elif "Error" in verdicts:
        overall_flag = "Error"
    else:
        overall_flag = "Clean"

    return {
        "overall_flag": overall_flag,
        "issues": contextualized
    }


# -------------------------------
# API Endpoints
# -------------------------------
@app.post("/check")
async def check_patient(patient: dict):
    """Check patient consistency from JSON body."""
    result = hybrid_consistency_check(patient)
    return JSONResponse(content=result)


@app.post("/check-file")
async def check_patient_file(file: UploadFile = File(...)):
    """Upload a JSON file with patient data."""
    try:
        data = json.loads(await file.read())
    except Exception:
        return JSONResponse(content={"error": "Invalid JSON file"}, status_code=400)

    result = hybrid_consistency_check(data)
    return JSONResponse(content=result)
