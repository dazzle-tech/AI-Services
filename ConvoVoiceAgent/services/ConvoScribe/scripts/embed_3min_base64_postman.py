"""Embed samples/visit_3min_sample.wav as audio_base64 in the Postman collection."""

from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAV_PATH = ROOT / "samples" / "visit_3min_sample.wav"
COLL_PATH = ROOT / "postman" / "ConvoScribe.postman_collection.json"
REQUEST_NAME = "Analyze Audio (Raw JSON) — 3 minute visit"


def main() -> None:
    b64 = base64.b64encode(WAV_PATH.read_bytes()).decode("ascii")
    payload = {
        "audio_base64": b64,
        "filename": "visit_3min_sample.wav",
        "context_type": "appointment",
        "attendees": ["doctor", "patient"],
        "purpose": "soap_note",
        "detail_level": "standard",
    }
    raw = json.dumps(payload, separators=(",", ":"))
    print(f"base64_chars={len(b64)} json_bytes={len(raw.encode('utf-8'))}")

    coll = json.loads(COLL_PATH.read_text(encoding="utf-8"))
    request = {
        "name": REQUEST_NAME,
        "request": {
            "method": "POST",
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "body": {
                "mode": "raw",
                "raw": raw,
                "options": {"raw": {"language": "json"}},
            },
            "url": {
                "raw": "{{baseUrl}}/api/v1/analyze",
                "host": ["{{baseUrl}}"],
                "path": ["api", "v1", "analyze"],
            },
            "description": (
                "JSON body for POST /api/v1/analyze. audio_base64 is the full "
                "samples/visit_3min_sample.wav clinic visit. The body is large; "
                "sending it may take a while. No auth headers."
            ),
        },
        "response": [],
    }

    items = [it for it in coll["item"] if it.get("name") != REQUEST_NAME]
    idx = next(
        (i for i, it in enumerate(items) if it.get("name") == "Analyze Audio — 3 minute visit"),
        None,
    )
    if idx is None:
        items.append(request)
    else:
        items.insert(idx + 1, request)
    coll["item"] = items
    coll["info"]["description"] = (
        "Postman collection for ConvoScribe.\n\n"
        "Only endpoint: **POST {{baseUrl}}/api/v1/analyze**\n\n"
        "Request styles:\n"
        "1. **Analyze Audio** — multipart form-data (file upload).\n"
        "2. **Analyze Audio — 3 minute visit** — form-data using visit_3min_sample.wav.\n"
        "3. **Analyze Audio (Raw JSON)** — tiny silent wav smoke test.\n"
        "4. **Analyze Audio (Raw JSON) — 3 minute visit** — full visit as audio_base64.\n\n"
        "**Setup**\n"
        "1. Set baseUrl.\n"
        "2. For form-data: select a .wav / .mp3 / .m4a file in audio.\n"
        "3. For JSON: use audio_base64 (the 3-minute visit request already includes the encoded file).\n\n"
        "**Auth**\n"
        "- No headers required. Send requests without X-API-Key or X-Clinician-Id."
    )
    COLL_PATH.write_text(json.dumps(coll, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {COLL_PATH} size={COLL_PATH.stat().st_size}")


if __name__ == "__main__":
    main()
