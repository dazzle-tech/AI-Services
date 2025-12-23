import subprocess
import json
import datetime
import re
from fastapi import FastAPI, Body
from pydantic import BaseModel
from typing import Dict, Any, List

# ====================================================
# JSON Extraction Utility
# ====================================================
def extract_json(text: str):
    """Extract and clean JSON from LLaMA/Ollama output."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        text = re.sub(r"//.*", "", text)   # remove // comments
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)  # remove /* ... */
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            candidate = match.group()
            try:
                return json.loads(candidate)
            except:
                pass
        return {"error": "Invalid JSON", "raw": text}


# ====================================================
# Compliance Checker Function
# ====================================================
def run_compliance(patient_data: Dict[str, Any], policies: List[str]) -> Dict[str, Any]:
    policies_str = ", ".join(policies)

    prompt = f"""
You are a strict compliance auditor. Analyze the following patient record against {policies_str}.

Patient record:
{json.dumps(patient_data, indent=2)}

Rules:
- HIPAA: Only mark violations if SharedExternally=true AND PatientConsent=false, except for emergencies or TPO (164.506).
- GDPR: Mark violations if consent is missing OR if there are cross-border transfers without safeguards.
- Hospital: Mark violations only if SharedExternally=true without proper approvals or encryption.
- If a framework is not requested in policies, ignore it completely.

Output format rules:
- For each violation, return an object with:
   {{
     "framework": "HIPAA" | "GDPR" | "Hospital",
     "violation": "short description",
     "article_or_rule": "legal citation"
   }}
- Do NOT output plain strings.
- If no violations, return [] for that framework.
- "all_violations" must merge all violations across frameworks.
- "compliant" = false if violations exist, true otherwise.

Output ONLY valid JSON in this format, nothing else:

{{
  "hipaa": [],
  "gdpr": [],
  "hospital": [],
  "all_violations": [],
  "compliant": true/false
}}
"""

    result = subprocess.run(
        ["ollama", "run", "llama3:8b", prompt],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore"
    )

    raw_output = result.stdout.strip()
    compliance_result = extract_json(raw_output)

    # Merge violations and compute compliance
    if "error" not in compliance_result:
        hipaa = compliance_result.get("hipaa", []) if "HIPAA" in policies else []
        gdpr = compliance_result.get("gdpr", []) if "GDPR" in policies else []
        hospital = compliance_result.get("hospital", []) if "Hospital" in policies else []
        all_violations = hipaa + gdpr + hospital
        compliance_result["all_violations"] = all_violations
        compliance_result["compliant"] = len(all_violations) == 0

    return {
        "input": patient_data,
        "policies_checked": policies,
        "compliance_result": compliance_result,
        "compliant": compliance_result.get("compliant", False),
        "timestamp_utc": datetime.datetime.now(datetime.UTC).isoformat()
    }


# ====================================================
# FastAPI Service
# ====================================================
app = FastAPI(title="Compliance Checker API")

class ComplianceRequest(BaseModel):
    policies: List[str]
    record: Dict[str, Any]

@app.post("/check_compliance")
def check_compliance(req: ComplianceRequest = Body(...)):
    return run_compliance(req.record, req.policies)
