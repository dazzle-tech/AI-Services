# ClinicalSummaryVoice

One speaker dictates a clinical summary. Send the audio; the service transcribes it and returns the summary. It does not separate speakers or build a SOAP conversation.

API: http://localhost:8039  
Docs: http://localhost:8039/docs

## Local development

```bash
cd ClinicalSummaryVoice
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Put a real `OPENAI_API_KEY` in `.env`, then:

```bash
python main.py
```

`.env` already lists every setting the service reads, including `OPENAI_MAX_RETRIES`.

## Sample and Postman

Spoken dictation: `samples/chest_pain_summary.wav` (text in `samples/chest_pain_summary.txt`).

Import `postman/ClinicalSummaryVoice.postman_collection.json`. Run **Health**, then **Summarize WAV**. The file is already attached. **Summarize JSON base64** sends the same recording without picking a file.

## Call

```bash
curl -X POST http://localhost:8039/api/v1/summarize ^
  -F "audio=@summary.wav"
```

Or JSON with `audio_base64` and optional `filename`.

Response:

```json
{
  "summary": "Patient is a 65-year-old male presenting with acute chest pain that started 2 hours ago. Blood pressure is 150/90, heart rate 95 bpm. Patient has history of hypertension and is currently taking Lisinopril 10mg daily. No known allergies. Assessment: Possible acute coronary syndrome. Plan: EKG, cardiac enzymes, aspirin 325mg.",
  "transcript": "..."
}
```

## Prompt

The summary model is instructed that the transcript is one person dictating, not a visit conversation. It may use only what was spoken, must keep doses, dates, and negations, and must not invent findings. The full text is in `app/ai/prompts.py` (`SUMMARY_SYSTEM_PROMPT`).

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_PORT` | `8039` | Server port |
| `OPENAI_API_KEY` | — | Required unless `USE_LLM_STUB=true` |
| `OPENAI_SUMMARY_MODEL` | `gpt-4o` | Writes the summary |
| `OPENAI_TRANSCRIBE_MODEL` | `gpt-4o-transcribe` | Speech to text |
| `USE_LLM_STUB` | `false` | Offline fixed summary for tests |

## Testing

```bash
pytest
```
clinical-summary-voice-service
