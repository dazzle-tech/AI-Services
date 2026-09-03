# ORVoiceAgent

Single integration point for each EMR **Record** button. Paths match **ORDisplayPlugin**; the client only talks to this service.

On a nursing sub-tab, call the matching path below. Voice is a WAV file or `audio_base64`. No LLM of its own.

### Nursing tab

Main tab name: **Nursing** (`role`: `Nursing` or `nurse`)

| Sub-tab | Path |
|---------|------|
| Verification of Marking Site | `POST /api/v1/windows/nursing/verification-of-marking-site` |
| Time Out | `POST /api/v1/windows/nursing/time-out` |
| Intraoperative | `POST /api/v1/windows/nursing/intraoperative` |
| Sign Out | `POST /api/v1/windows/nursing/sign-out` |

### Other tabs

| Tab | Path |
|-----|------|
| Anesthesia — Pre-evaluation / plan | `POST /api/v1/windows/anesthesia/pre-evaluation-plan` |
| Anesthesia — Induction / intraoperative | `POST /api/v1/windows/anesthesia/induction-intraoperative` |
| Anesthesia — Observation and drugs | `POST /api/v1/windows/anesthesia/observation-drugs` |
| Operative Note | `POST /api/v1/windows/operative-note` |

Workflow for each nursing sub-tab:

1. Sends the voice to **ORScribe** (`POST /api/v1/windows/transcribe`)
2. Sends the returned text to the **same path** on **ORDisplayPlugin**
3. Returns DisplayPlugin’s JSON as the final response (unwrapped EMR shape per sub-tab)

API: http://localhost:8035  
Docs: http://localhost:8035/docs

## Local development

```bash
cd ORVoiceAgent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env

python main.py
```

Run ORScribe on **8030** and ORDisplayPlugin on **8032**.

## Example — Time Out tab

Multipart WAV:

```bash
curl -X POST http://localhost:8035/api/v1/windows/nursing/time-out \
  -F "audio=@clip.wav"
```

JSON base64:

```bash
curl -X POST http://localhost:8035/api/v1/windows/nursing/time-out \
  -H "Content-Type: application/json" \
  -d "{\"audio_base64\":\"...\",\"filename\":\"clip.wav\"}"
```

No request headers. JSON fields: `audio_base64`, optional `filename`. Multipart can use `audio_base64` instead of `audio`.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_PORT` | `8035` | Server port |
| `ORSCRIBE_BASE_URL` | `http://localhost:8030` | Transcription |
| `ORDISPLAY_BASE_URL` | `http://localhost:8032` | Window field fill |
| `HTTP_TIMEOUT_SECONDS` | `60` | Outbound timeout |

## Postman

Import `postman/ORVoiceAgent.postman_collection.json`.

Each window has **WAV file** and **JSON base64**. WAV is pre-selected as `ORScribe/samples/or_case_sample.wav`. Open **Example 200** under a request to see the typical final JSON.

**Time Out (full example)**

- Method: `POST`
- URL: `http://localhost:8035/api/v1/windows/nursing/time-out`
- No auth headers
- Body (form-data): `audio` = a `.wav`

Or JSON:

```json
{
  "audio_base64": "<base64 of a .wav>",
  "filename": "clip.wav"
}
```

Typical 200 from Time Out (`POST /api/v1/windows/nursing/time-out`) — checklist and staff only, no wrapper:

```json
{
  "checklist": [
    {
      "key": "correct_patient",
      "label": "Correct Patient",
      "checked": true,
      "note": "Confirmed by wristband"
    },
    {
      "key": "correct_procedure",
      "label": "Correct Procedure",
      "checked": true,
      "note": "Right total knee replacement"
    },
    {
      "key": "correct_site_and_side",
      "label": "Correct Site and Side",
      "checked": true,
      "note": ""
    },
    {
      "key": "correct_patient_position",
      "label": "Correct Patient Position",
      "checked": true,
      "note": "Supine"
    },
    {
      "key": "verification_of_site_markings",
      "label": "Verification of site markings",
      "checked": true,
      "note": ""
    },
    {
      "key": "availability_of_correct_implants_equipment",
      "label": "Availability of correct implants / special equipment",
      "checked": true,
      "note": "Size 4 tray open"
    }
  ],
  "staff": {
    "surgeon": {
      "staffId": "stf_2041",
      "displayName": "Dr. Omar Haddad"
    },
    "nurse": {
      "staffId": "stf_5590",
      "displayName": "Lina Odeh"
    }
  }
}
```

## Testing

```bash
pytest
```
