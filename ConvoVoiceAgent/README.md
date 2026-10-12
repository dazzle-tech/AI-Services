# ConvoVoiceAgent

Single call for a doctor–patient recording. The client talks only to this service.

1. Sends the audio to **ConvoScribe** (`POST /api/v1/analyze`) for transcript, speaker roles, and the clinical note.
2. Sends that note to **SystemDisplayPlugin** (`POST /api/v1/reshape`) to fill the requested views.
3. Returns DisplayPlugin’s JSON as the response.

API: http://localhost:8036  
Docs: http://localhost:8036/docs

`python main.py` starts ConvoScribe on **8026** and SystemDisplayPlugin on **8031** when those ports are not already up. Their code is unchanged under `services/`. A service that is already running is left as it is, and it is not stopped when the agent exits.

## Local development

```bash
cd ConvoVoiceAgent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env

python main.py
```

## Example

Multipart audio:

```bash
curl -X POST http://localhost:8036/api/v1/analyze ^
  -F "audio=@visit.wav" ^
  -F "context_type=appointment" ^
  -F "purpose=soap_note" ^
  -F "view_ids=soap_note"
```

JSON base64:

```bash
curl -X POST http://localhost:8036/api/v1/analyze ^
  -H "Content-Type: application/json" ^
  -d "{\"audio_base64\":\"...\",\"filename\":\"visit.wav\",\"view_ids\":[\"soap_note\"]}"
```

Optional fields: `context_type` (default `appointment`), `purpose` (default `soap_note`), `detail_level` (default `standard`), `view_ids` (default `soap_note`). Multipart `view_ids` may be comma-separated or a JSON array.

The response is the display result:

```json
{
  "results": [
    {
      "view_id": "soap_note",
      "data": {
        "ChiefComplaint": "Headache",
        "Assessments": "Tension headache."
      },
      "warnings": []
    }
  ]
}
```

ConvoScribe’s SOAP fields (`subjective`, `objective`, `assessment`, `plan`) are what SystemDisplayPlugin maps. A narrative summary or clinical document is flattened onto those same fields before the reshape call.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_PORT` | `8036` | Server port |
| `CONVOSCRIBE_BASE_URL` | `http://localhost:8026` | Transcript and clinical note |
| `SYSTEM_DISPLAY_BASE_URL` | `http://localhost:8031` | View mapping |
| `HTTP_TIMEOUT_SECONDS` | `180` | Outbound timeout for both calls |
| `DEFAULT_VIEW_IDS` | `soap_note` | Views used when the request omits `view_ids` |

## Testing

```bash
pytest
```
