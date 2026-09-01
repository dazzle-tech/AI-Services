# ORScribe sample audio

## `or_case_sample.wav`

Multi-speaker operating room conversation (~55s) covering:

- WHO sign-in, time-out, and sign-out
- Surgeon, anesthetist, and nurse dialogue
- Vitals report, medication (propofol 100 mg), and instrument counts

Regenerate:

```bash
py scripts/generate_sample_audio.py
```

On Windows uses built-in SAPI voices. On Linux/macOS uses `pyttsx3`. A silent placeholder is written if TTS fails.

## Quick test (API running on port 8030)

One-shot (no polling):

```bash
curl -X POST http://localhost:8030/api/v1/analyze \
  -H "X-API-Key: change-me-to-a-secure-random-key" \
  -H "X-Staff-Id: nurse-1" \
  -F "audio=@samples/or_case_sample.wav"
```

Async case:

```bash
curl -X POST http://localhost:8030/api/v1/cases \
  -H "X-API-Key: change-me-to-a-secure-random-key" \
  -H "X-Staff-Id: nurse-1" \
  -F "procedure_type=laparoscopic cholecystectomy" \
  -F "ingest_mode=post_hoc" \
  -F "audio=@samples/or_case_sample.wav"
```

Poll `GET /api/v1/cases/{case_id}` until `status` is `completed`.

**Note:** With `TRANSCRIPTION_BACKEND=stub`, the pipeline uses a fixed transcript regardless of audio content. Use `whisper_pyannote` in production to transcribe real audio.
