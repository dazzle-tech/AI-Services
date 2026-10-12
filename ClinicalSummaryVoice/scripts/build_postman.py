"""Build the Postman collection around the spoken chest-pain sample."""

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAV = ROOT / "samples" / "chest_pain_summary.wav"
OUT = ROOT / "postman" / "ClinicalSummaryVoice.postman_collection.json"

b64 = base64.b64encode(WAV.read_bytes()).decode("ascii")
example = {
    "summary": (
        "Patient is a 65-year-old male presenting with acute chest pain that started 2 hours ago. "
        "Blood pressure is 150/90, heart rate 95 bpm. Patient has history of hypertension and is "
        "currently taking Lisinopril 10mg daily. No known allergies. Assessment: Possible acute "
        "coronary syndrome. Plan: EKG, cardiac enzymes, aspirin 325mg."
    ),
    "transcript": "...",
}
collection = {
    "info": {
        "name": "ClinicalSummaryVoice",
        "description": (
            "One speaker dictates a clinical summary. POST the WAV; the response summary is one "
            "paragraph ending with Assessment and Plan.\n\n"
            "Default audio: samples/chest_pain_summary.wav\n"
            "Start the service with python main.py at http://localhost:8037."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "variable": [
        {"key": "baseUrl", "value": "http://localhost:8037"},
        {"key": "audioBase64", "value": b64},
    ],
    "item": [
        {
            "name": "Health",
            "request": {
                "method": "GET",
                "header": [],
                "url": "{{baseUrl}}/api/v1/health",
                "description": "Checks that the service is up and OpenAI is configured.",
            },
        },
        {
            "name": "Summarize WAV",
            "request": {
                "method": "POST",
                "header": [],
                "body": {
                    "mode": "formdata",
                    "formdata": [
                        {
                            "key": "audio",
                            "type": "file",
                            "src": str(WAV),
                            "description": "Spoken chest-pain dictation.",
                        }
                    ],
                },
                "url": "{{baseUrl}}/api/v1/summarize",
                "description": "Multipart file upload. Returns summary and transcript.",
            },
            "response": [
                {
                    "name": "Example 200",
                    "originalRequest": {
                        "method": "POST",
                        "header": [],
                        "url": "{{baseUrl}}/api/v1/summarize",
                    },
                    "status": "OK",
                    "code": 200,
                    "_postman_previewlanguage": "json",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": json.dumps(example, indent=2),
                }
            ],
        },
        {
            "name": "Summarize JSON base64",
            "request": {
                "method": "POST",
                "header": [{"key": "Content-Type", "value": "application/json"}],
                "body": {
                    "mode": "raw",
                    "raw": '{\n  "audio_base64": "{{audioBase64}}",\n  "filename": "chest_pain_summary.wav"\n}',
                    "options": {"raw": {"language": "json"}},
                },
                "url": "{{baseUrl}}/api/v1/summarize",
                "description": "Same sample as base64. audioBase64 is chest_pain_summary.wav.",
            },
        },
    ],
}

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(collection, indent=2), encoding="utf-8")
print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
