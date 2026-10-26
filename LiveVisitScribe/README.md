# LiveVisitScribe

Live transcript for a clinical visit, on port **8037**. While the doctor is still talking, the browser streams microphone audio over a WebSocket. This service sends back transcript lines as they are spoken, plus a "Picked up so far" list.

It stores nothing: no database, no audio files, no visits. The only state is the open WebSocket, held in memory and dropped when it closes. Asklepios owns consent, the recording, and the chart. **Every message here is provisional and is not the chart note.**

## How it fits with ConvoVoiceAgent

| While the red bar is running | After "Stop & create draft" |
|---|---|
| Browser streams audio to `ws://localhost:8037/api/v1/live` (this service) | Browser sends the **same full recording** to ConvoVoiceAgent `POST http://localhost:8036/api/v1/draft` |
| Live lines + "Picked up so far" | The sourced SOAP draft, diagnoses, orders |

This service never calls ConvoVoiceAgent; the browser does that on Stop. The speaker on a finished line is assigned by the same model that builds "Picked up so far". The note still comes from `/draft`.

Not related to `STT_Service` (port 8027), which is radiology dictation.

## Run

```powershell
cd LiveVisitScribe
python -m pip install -r requirements.txt
copy .env.example .env
python main.py
```

`USE_LLM_STUB=true` runs with no Whisper model and no API key: it returns scripted lines and a deterministic picked-up list (this is what the tests use). Otherwise set `OPENAI_API_KEY` for the picked-up list; the first run downloads the Whisper model. `ENABLE_DEV_PAGES=true` serves the browser page at `/try` and the API docs. A deployed instance leaves it false.

Tests: `python -m pytest -q`

## Docker

```powershell
cd LiveVisitScribe
copy .env.example .env     # optional; set OPENAI_API_KEY for the picked-up list
docker compose up --build  # serves ws://localhost:8037/api/v1/live
```

- Plain image: `docker build -t live-visit-scribe .` then `docker run -p 8037:8037 -v live_models:/models live-visit-scribe`.
- Wiring check with no model and no key: `USE_LLM_STUB=true docker compose up --build`.
- The Whisper model is downloaded on first start into the `/models` volume, so later starts are fast. The healthcheck allows 2 minutes for that first start.
- The container runs on CPU by default (`WHISPER_DEVICE=cpu`). A GPU override is `docker-compose.gpu.yml` with `Dockerfile.gpu`. **`Dockerfile.gpu` has not been built or run.**
- No ffmpeg is installed: the browser sends raw PCM, not an audio container.
- The image has not been built in CI yet; if you change `requirements.txt`, rebuild with `--build`.

## Postman and a test client

- `postman/LiveVisitScribe.postman_collection.json`: `GET /` and `GET /api/v1/health` with saved examples, and a reference item with every WebSocket message (client `start`; server `ready`, partial and final `segment`, Arabic + English `mixed`, `picked_up`, `paused`, `resumed`, `final`, `error`). A Postman collection file cannot hold a WebSocket request, so open **New > WebSocket** in Postman, connect to `ws://localhost:8037/api/v1/live`, and paste the messages from the collection description.
- `scripts/stream_wav.py`: plays a 16-bit WAV into the socket at real-time pace, the way the browser microphone does, and prints lines and the picked-up list as they arrive:

```powershell
python scripts/stream_wav.py ..\ConvoVoiceAgent\services\ConvoScribe\samples\visit_sample.wav
python scripts/stream_wav.py visit.wav --speed 2 --url ws://localhost:8037/api/v1/live
```

  With `USE_LLM_STUB=true` the lines are the scripted ones whatever the audio says.

## WebSocket: `ws://localhost:8037/api/v1/live`

Client to server:

| Frame | Meaning |
|---|---|
| text `{"type":"start","sample_rate":16000,"channels":1,"patient_context":{...}}` | Begin. `sample_rate` 8000-48000, `channels` 1 or 2. `patient_context` is optional: `{chronic_diseases, active_medications, allergies, known_diagnoses}` |
| **binary** | Raw little-endian **int16 PCM**, interleaved if 2 channels. Any frame size (100-250 ms is typical). Audio before `start` returns an error |
| text `{"type":"pause"}` / `{"type":"resume"}` | Pause: the open line is closed and audio is ignored until resume |
| text `{"type":"stop"}` | End: the open line is closed, the list is flushed, `final` is sent, the socket closes |

Server to client (text JSON):

| Message | Shape |
|---|---|
| `ready` | `{"type":"ready","sample_rate":16000,"channels":1}` |
| `segment` | `{"type":"segment","id":"t1","speaker":"doctor\|patient","start_ms":0,"end_ms":4200,"text":"...","lang":"en\|ar\|mixed","final":false,"low_confidence_numbers":[]}`. The same `id` is sent again with `final:true` when the line ends, and again when the model corrects `speaker`. `low_confidence_numbers` lists digit-bearing words Whisper was unsure of (empty unless `WHISPER_WORD_CONFIDENCE` is on) |
| `warning` | `{"type":"warning","detail":"session_length","seconds":2700}` once, as the visit nears `MAX_SESSION_SECONDS`. `{"type":"warning","detail":"No audio received; ending the session."}` when the socket goes quiet; that one is followed by `final` |
| `picked_up` | `{"type":"picked_up","complaint":{"text","segment_ids"}\|null,"symptoms":[{"text","segment_ids"}],"medications":[{"name","detail","confirm":true,"segment_ids"}],"exam":[{"text","segment_ids"}],"record":{...},"record_evidence":{...},"record_status":{...},"missing_required":{...}}` (see "Record payloads") |
| `paused` / `resumed` | Acknowledge `pause` / `resume`. Every `segment` before `paused` is already final |
| `final` | `{"type":"final","segments":[...],"audio_ms":272000}` (all final lines in order) |
| `error` | `{"type":"error","detail":"..."}`. Bad input errors keep the socket open |

Browser framing: capture with an `AudioWorklet`, convert each `Float32Array` block to `Int16Array` (`Math.max(-1, Math.min(1, x)) * 32767`), and `ws.send(int16.buffer)`. Declare the context's real `sampleRate` in `start`; the service resamples to 16 kHz.

### Lines

- Speech starts a line. While it continues, a partial (`final:false`, same `id`) is refreshed every `STREAM_CHUNK_SECONDS` by transcribing the line so far, and the text is **replaced**, not appended.
- `SILENCE_MS` (800 ms) of silence ends the line: it is sent once more with `final:true`. Ids are `t1`, `t2`, ... in order; noise bursts and empty results do not use an id.
- A line longer than `MAX_TURN_SECONDS` is split; `STREAM_OVERLAP_SECONDS` of audio is carried into the next line so a word on the cut is not lost (a repeated word at the cut is possible).
- If the service falls more than `MAX_BACKLOG_SECONDS` behind real time, partials are skipped until it catches up. Final lines are never skipped.
- `start_ms` / `end_ms` count the audio received while not paused, so they match a recording whose recorder is also paused.
- `lang` comes from the characters in the line: Arabic only is `ar`, Latin only is `en`, both is `mixed` (a drug name inside Arabic speech makes it `mixed`).
- `speaker` is `doctor` or `patient`. While a line is still being spoken the label is a guess from the words (a tie goes to the patient). Once the line is final, the picked-up model assigns the role and the line is sent again with the same `id`. One microphone cannot reliably separate two voices.

### Picked up so far

A scratch list for the doctor, not a note. It is updated at most every `PICKED_UP_INTERVAL_SECONDS` (8 s), only when a new final line arrived, with one small JSON model call over the final lines (or the stub). That call also returns a speaker for each finished line. The last update is flushed on `stop`. A `picked_up` message is sent only when the list changed. A corrected speaker is sent even when the list is unchanged.

Whatever the model returns, `app/live/picked_up.py` enforces these before anything is sent:

- An item must cite a final segment id. Unknown ids are removed; an item with no valid id is dropped.
- An item cited only by question lines is dropped (a question is not a finding or a negative).
- A medicine must be named in a cited segment (a whole word, so "iron" is not found inside "environment"; an Arabic name may match inside ال / بال). Its `detail` is kept only when every number, unit and frequency in it was said; a changed frequency or a different unit clears `detail` and keeps the medicine, still with `confirm: true`.
- An exam finding's numbers must appear in a cited segment. Arabic-Indic and Persian digits count as the same numbers.
- A complaint, symptom or exam item is dropped when the cited words deny it ("No." after "Any chest pain?"). An item that already says the denial ("No aura") stays.
- An item that only restates `patient_context` (a chart diagnosis, allergy or regular medicine not said in the visit) is dropped.

The prompt (`app/live/picked_up_prompts.py`) also tells the model to copy words, numbers and drug names as spoken, keep a misheard drug as heard, keep a relative's report as theirs, and never infer negatives. If the model is not configured or fails, one `error` is sent ("Picked up so far could not be updated") and the live lines continue.

### Record payloads

`picked_up` also carries the visit so far in the shapes Asklepios posts, the same shapes as ConvoVoiceAgent `/draft` `record`, so the panel can show real fields filling in:

- `record.vital_sign`, `body_measurements`, `pain_assessment`, `nursing_assessment`, `clinical_visit`, `assessment`, `plan_of_care`. A group is `null` until something is found for it. Missing values are `null`; the constants are only `isActive: true`, `isTriage: false`, `byPatient: true`, `priorityLevel: "NORMAL"`, and `painAssessmentType: "NUMERIC"` once a pain score is said.
- `record_status`: `empty`, `partial` or `complete` per group. `missing_required` lists the required fields not said yet (vitals: blood pressure both numbers, heart rate, temperature, oxygen saturation, respiratory rate; measurements: weight and height; pain: `painDegree`; nursing: `reasonOfVisit`), so the UI can show "still needed" as the visit goes.
- `record_evidence`: `"group.field"` to the segment ids it was heard in.
- `clinical_visit` and `nursing_assessment.reasonOfVisit` are built from the complaint, symptoms and exam lists above (already checked). The measured fields come from the model and pass the checks in `app/live/asklepios.py` (identical to ConvoVoiceAgent's copy): a cited non-question segment, a number that was actually said, a plausible range, enum values from the backend table whose cited line talks about that topic, and systolic above diastolic.
- There is no `patient_diagnosis`: ICD-10 coding is ConvoVoiceAgent's job when the visit is stopped. The enum tables in `app/live/asklepios.py` mark which values are confirmed from the backend samples and which are assumed.

## Configuration

See `.env.example`.

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `8037` | HTTP / WebSocket port |
| `WHISPER_MODEL` | `small` | `tiny` / `base` / `small` / `medium` / `large-v3`. Larger reads Arabic better but needs a GPU to keep up live |
| `WHISPER_DEVICE` | `auto` | `auto` / `cuda` / `cpu` |
| `WHISPER_LANGUAGE` | blank | Blank = auto-detect |
| `STREAM_CHUNK_SECONDS` | `4` | Partial refresh interval |
| `STREAM_OVERLAP_SECONDS` | `0.5` | Audio carried over when a long line is split |
| `SILENCE_MS` / `SILENCE_RMS` | `800` / `0.01` | End-of-line silence and the energy below which a frame is silence |
| `PICKED_UP_INTERVAL_SECONDS` | `8` | Minimum gap between list updates |
| `LIVE_EXTRACT_MODEL` | `gpt-4o-mini` | Model for the list |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` | blank | Any OpenAI-compatible endpoint |
| `USE_LLM_STUB` | `false` | `true` = scripted lines and deterministic list, no model and no key |
| `MAX_SESSIONS` | `8` | Live visits this process will hold. One more is refused with `busy` |
| `MAX_SESSION_SECONDS` | `3600` | Audio seconds (pause time does not count) before the visit is ended with `final` |
| `SESSION_WARN_SECONDS` | `2700` | One `session_length` warning |
| `START_TIMEOUT_SECONDS` | `10` | Close if `start` never arrives |
| `IDLE_TIMEOUT_SECONDS` | `30` | No audio while running: warning, then `final` |
| `PAUSE_TIMEOUT_SECONDS` | `900` | Close a visit left on pause |
| `MAX_FRAME_BYTES` | `524288` | One binary frame larger than this is refused |
| `MAX_BACKLOG_HARD_SECONDS` | `30` | Queued audio past this closes the visit. `MAX_BACKLOG_SECONDS` still only skips partials |
| `WHISPER_LANGUAGES` | `ar,en` | Detections outside this list are remapped |
| `WHISPER_INITIAL_PROMPT` | blank | Hint passed to Whisper. Blank sends none |
| `WHISPER_NO_SPEECH_THRESHOLD` | `0.6` | With a poor logprob, drop the piece. Missing scores are kept |
| `WHISPER_MIN_AVG_LOGPROB` | `-1.0` | See above |
| `WHISPER_MAX_COMPRESSION_RATIO` | `2.4` | Drop a repeated hallucination |
| `WHISPER_WORD_CONFIDENCE` | `false` | Ask for per-word probabilities and fill `low_confidence_numbers` |
| `WHISPER_LOW_CONFIDENCE` | `0.6` | A digit-bearing word under this probability is flagged |
| `PICKED_UP_MAX_INTERVAL_SECONDS` | `30` | The update gap grows with the number of finished lines, up to this |
| `EXTRACT_MAX_CONCURRENCY` | `4` | Picked-up model calls in flight in this process |
| `STOP_FLUSH_TIMEOUT_SECONDS` | `45` | On stop, wait this long for the last update, then send `final` anyway |
| `OPENAI_MAX_RETRIES` | `2` | Retries of that model call |
| `ENABLE_DEV_PAGES` | `false` | `true` serves `/try`, `/docs`, `/redoc` and `/openapi.json` |

## Limits to know

- Whisper reads one language per pass, so a sentence that switches between Arabic and English can lose words. Check on real recordings; `/draft` re-transcribes the full audio afterwards.
- Each partial transcribes the whole line so far (up to `MAX_TURN_SECONDS`), so CPU-only machines may fall behind on long lines; backlog skipping keeps final lines coming.
- Auth and TLS are the gateway's job. This service does not check a caller.

## Production notes

| Endpoint | Role |
|---|---|
| `GET /api/v1/health` | Liveness. The process is up. It does not look at capacity or whether a model loaded |
| `GET /api/v1/ready` | Readiness. `200` with `{ready, problems, sessions_active, sessions_max, full}` when speech is loaded, the picked-up model is configured, and a slot is free. `503` with the same body otherwise |
| `GET /api/v1/metrics` | Prometheus text, prefix `livescribe_`. Counts and timings only |

Alert when `livescribe_asr_last_rtf` stays above `0.7` for several minutes (speech is slower than the audio). Alert when `livescribe_sessions_rejected_total`, `livescribe_partials_skipped_total` or `livescribe_extract_failures_total` keeps rising.

Limits: `MAX_SESSIONS` refuses another visit (`busy`, close `1013`). `MAX_SESSION_SECONDS` sends a `session_length` warning at `SESSION_WARN_SECONDS`, then ends the visit with `final`. No audio for `IDLE_TIMEOUT_SECONDS` sends `No audio received; ending the session.` and still sends `final`. A frame over `MAX_FRAME_BYTES` closes with `1009`. Queued audio over `MAX_BACKLOG_HARD_SECONDS` closes with `busy` and `1013`; the smaller `MAX_BACKLOG_SECONDS` only skips partials. `low_confidence_numbers` on a segment lists digit-bearing words below `WHISPER_LOW_CONFIDENCE` when word timestamps are on.

The gateway's WebSocket read timeout should be longer than `IDLE_TIMEOUT_SECONDS`, or it will cut a quiet visit before this service can send `final`. Drain an instance before a deploy: stop sending it new visits, wait for the open ones to send `final`, then stop the process (`stop_grace_period` is 15s).

The picked-up list drops a dose detail whose number, unit or frequency was not said, drops a medicine name that is only part of a longer Latin word, and drops a complaint, symptom or exam line that the cited words deny.

Not done here:

- Word error rate on real Saudi Arabic and mixed audio.
- A load test to choose `MAX_SESSIONS`.
- Building or running `Dockerfile.gpu`.
- A lock file and `pip-audit` in CI (`requirements.txt` only has upper bounds).
- Moving the picked-up model in-Kingdom. Point `OPENAI_BASE_URL` at that endpoint when it exists.
