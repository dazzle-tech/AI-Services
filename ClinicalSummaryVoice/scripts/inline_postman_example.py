"""Inline the spoken sample into the JSON Postman request and save an example response."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / "postman" / "ClinicalSummaryVoice.postman_collection.json"

data = json.loads(COLLECTION.read_text(encoding="utf-8"))
audio_b64 = next(item["value"] for item in data["variable"] if item["key"] == "audioBase64")
example_body = {
    "summary": (
        "Patient is a 65-year-old male presenting with acute chest pain that started 2 hours ago. "
        "Blood pressure is 150/90, heart rate 95 bpm. Patient has history of hypertension and is "
        "currently taking Lisinopril 10mg daily. No known allergies. Assessment: Possible acute "
        "coronary syndrome. Plan: EKG, cardiac enzymes, aspirin 325mg."
    ),
    "transcript": (
        "Patient is a 65 year old male presenting with acute chest pain that started 2 hours ago. "
        "Blood pressure is 150 over 90. Heart rate 95 beats per minute. "
        "Patient has a history of hypertension and is currently taking Lisinopril 10 milligrams daily. "
        "No known allergies. Assessment, possible acute coronary syndrome. "
        "Plan, EKG, cardiac enzymes, aspirin 325 milligrams."
    ),
}

raw = json.dumps(
    {"audio_base64": audio_b64, "filename": "chest_pain_summary.wav"},
    indent=2,
)

for item in data["item"]:
    if item["name"] != "Summarize JSON base64":
        continue
    item["request"]["body"]["raw"] = raw
    item["request"]["description"] = (
        "Full example. audio_base64 is the complete chest_pain_summary.wav recording, "
        "not a variable. The saved example shows the summary paragraph the service should return."
    )
    item["response"] = [
        {
            "name": "Example 200",
            "originalRequest": {
                "method": "POST",
                "header": [{"key": "Content-Type", "value": "application/json"}],
                "body": {
                    "mode": "raw",
                    "raw": raw,
                    "options": {"raw": {"language": "json"}},
                },
                "url": "{{baseUrl}}/api/v1/summarize",
            },
            "status": "OK",
            "code": 200,
            "_postman_previewlanguage": "json",
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "body": json.dumps(example_body, indent=2),
        }
    ]

COLLECTION.write_text(json.dumps(data, indent=2), encoding="utf-8")
print("updated", COLLECTION.stat().st_size)
