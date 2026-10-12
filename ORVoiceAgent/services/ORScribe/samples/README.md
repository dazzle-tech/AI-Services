# ORScribe sample audio

## `pre_eval_test.wav`

Clear single-speaker anesthesia pre-evaluation dictation (~32s) for ORVoiceAgent /
`gpt-4o-transcribe` smoke tests. Also copied to `ORVoiceAgent/postman/pre_eval_test.wav`
and `ORVoiceAgent/postman/pre_eval_test.json` (base64 body).

```bash
curl -X POST http://localhost:8035/api/v1/windows/anesthesia/pre-evaluation-plan `
  -F "audio=@ORVoiceAgent/postman/pre_eval_test.wav"
```

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
  -F "audio=@samples/or_case_sample.wav"
```

Async case:

```bash
curl -X POST http://localhost:8030/api/v1/cases \
  -F "procedure_type=laparoscopic cholecystectomy" \
  -F "ingest_mode=post_hoc" \
  -F "audio=@samples/or_case_sample.wav"
```

Poll `GET /api/v1/cases/{case_id}` until `status` is `completed`.

**Note:** With `TRANSCRIPTION_BACKEND=stub`, the pipeline uses a fixed transcript regardless of audio content. Use `TRANSCRIPTION_BACKEND=openai` (`gpt-4o-transcribe`) for cloud STT.
