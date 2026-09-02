# STT Service — Specialized Speech-to-Text for Radiology

Standalone, local Whisper-based STT microservice tailored for radiology dictation. Implements
the spec in `docs/Project Specification_ Specialized Speech-to-Text for Radiology.pdf`.

This is a pure backend API with no UI — designed to be called by other services
(e.g. a chatbot orchestrator) over REST or WebSocket.

- **Local-only inference** — audio never leaves the host (HIPAA-friendly).
- **Whisper backend** via `faster-whisper` (CTranslate2), GPU (CUDA) or CPU.
- **Radiology specialization** via an `initial_prompt` lexicon + regex-based post-processing
  (e.g. `T 1 weighted` → `T1-weighted`, `MM` units, modality casing).
- **REST + WebSocket** — upload a complete file, send single chunks, or stream live audio.

## Service port

Default: **8027** (env: `PORT`).

## Layout

```
STT_Service/
  api/
    app/
      main.py
      config.py
      core/      (whisper_engine, audio_processor, radiology_postprocess)
      routes/    (transcribe REST + websocket)
      models/    (pydantic schemas)
    prompts/
      radiology_lexicon.txt
    tests/
      test_live_mic.py               # Python CLI for mic/file/WS testing
    requirements.txt
    .env.example
    run.py
  docs/
    Project Specification_*.pdf
```

## Setup

### 1. System prerequisites

- **Python 3.11.15**
- **FFmpeg** on PATH — used to decode uploaded audio (any container/codec) to 16 kHz mono PCM.
  - Windows: download from https://www.gyan.dev/ffmpeg/builds/ and add the `bin\` folder to PATH.
- **(Optional) NVIDIA GPU with CUDA 12.x** for accelerated inference. The service auto-detects
  CUDA and falls back to CPU if unavailable.

### 2. Python deps

```powershell
cd C:\Users\adama\Projects\Work\AI-services\STT_Service\api
python -m pip install -r requirements.txt
```

> If you have an NVIDIA GPU and want CUDA: also install `cuDNN` + `cuBLAS` matching your CUDA
> runtime. `faster-whisper` uses them via CTranslate2.

### 3. Config

```powershell
copy .env.example .env
```

Edit `.env`. Most useful knobs:

| Var | Default | Meaning |
|-----|---------|---------|
| `PORT` | `8027` | HTTP port |
| `WHISPER_MODEL` | `medium` | `tiny` / `base` / `small` / `medium` / `large-v2` / `large-v3` |
| `WHISPER_DEVICE` | `auto` | `auto` / `cuda` / `cpu` |
| `WHISPER_COMPUTE_TYPE` | (auto) | `float16` / `int8_float16` (GPU); `int8` / `float32` (CPU) |
| `WHISPER_LANGUAGE` | `en` | Language hint; leave blank for auto-detect |
| `RADIOLOGY_PROMPT_PATH` | `prompts/radiology_lexicon.txt` | Initial prompt biasing |
| `STREAM_CHUNK_SECONDS` | `4.0` | Window size for live streaming |
| `STREAM_OVERLAP_SECONDS` | `0.5` | Overlap between live windows |
| `MAX_UPLOAD_MB` | `200` | REST upload cap |

### 4. Run

```powershell
cd C:\Users\adama\Projects\Work\AI-services\STT_Service\api
python run.py
```

First run downloads the model weights to your HuggingFace cache (`~/.cache/huggingface`),
so expect a one-time wait. Subsequent starts are fast.

## Integrating with a chatbot / other service

The service is a plain FastAPI app with no dependency on any frontend. Call it like any
internal microservice:

- REST: `POST /api/v1/transcribe` (full file) or `/api/v1/transcribe/chunk` (single chunk)
  from your chatbot's backend, passing the recorded audio as multipart form data.
- WebSocket: `WS /api/v1/ws/transcribe` for live streaming transcription during a call/session.
- CORS is currently wide open (`allow_origins=["*"]`) for ease of integration — tighten this
  in `api/app/main.py` to your chatbot's actual origin(s) before deploying beyond local dev.

## API

OpenAPI docs once the server is running: <http://localhost:8027/docs>

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/` | Service info |
| `GET`  | `/api/v1/health` | Status, model, device, FFmpeg+prompt readiness |
| `POST` | `/api/v1/transcribe` | Multipart file upload → full transcription |
| `POST` | `/api/v1/transcribe/chunk` | Multipart single chunk → quick transcription (beam=1) |
| `WS`   | `/api/v1/ws/transcribe` | Live streaming (control JSON + int16 PCM binary frames) |

### `POST /api/v1/transcribe` form fields

| Field | Type | Notes |
|-------|------|-------|
| `file` | file | wav / mp3 / m4a / webm / ogg / flac |
| `language` | string | optional, e.g. `en` |
| `extra_prompt` | string | optional case context to bias decoder (e.g. "Chest CT in 58M") |
| `beam_size` | int | 1-10, default 5 |
| `include_raw_text` | bool | if true, response also includes pre-postprocessing text |

Response: `text`, `raw_text` (optional), `language`, `language_probability`,
`audio_duration_seconds`, `inference_seconds`, `segments[]`, `model`, `device`.

### WebSocket protocol — `/api/v1/ws/transcribe`

1. Connect — server sends `{"type": "hello", ...}`.
2. Send control JSON: `{"type":"start","sample_rate":16000,"channels":1,"language":"en","extra_prompt":"..."}`.
3. Server replies `{"type":"ready", ...}`.
4. Send binary frames of **little-endian int16 PCM** at the declared sample rate.
5. Receive `{"type":"partial","text":"...", ...}` every ~`STREAM_CHUNK_SECONDS`.
6. Send `{"type":"stop"}` (or just close). Server returns `{"type":"final", ...}`.

## Testing

### Postman (REST)

Import the unified repo collection at [../postman_collection.json](../postman_collection.json) → **STT_Service** folder. Set `stt_service_base_url` to `http://localhost:8027`.

> **Postman cannot record audio from your microphone**, so the WebSocket request in the
> collection is documentation only. Use the Python script below for live mic testing.

### Python script (mic + file + WebSocket)

```powershell
cd C:\Users\adama\Projects\Work\AI-services\STT_Service\api

# 1) Upload an existing file
python tests\test_live_mic.py file --path path\to\dictation.wav --extra-prompt "Chest CT, 58M, smoker."

# 2) Record 12s from default mic, save to WAV, then upload
python tests\test_live_mic.py record --seconds 12 --out recorded.wav

# 3) Live streaming over WebSocket (partial transcriptions, then final)
python tests\test_live_mic.py stream --seconds 20 --extra-prompt "Brain MRI, R/O acute stroke."
```

## Notes & limitations

- The default model is `medium` for a sensible CPU-friendly baseline. For best clinical
  accuracy switch `WHISPER_MODEL=large-v3` (requires GPU for real-time speeds).
- LoRA fine-tuning is *not* included here (it requires a labeled radiology corpus). The
  service is structured so a fine-tuned CTranslate2 checkpoint can be dropped in via
  `WHISPER_MODEL=/abs/path/to/ct2-model-dir`.
- Streaming uses a sliding-window approach for partials and re-runs the full audio at
  the end (beam=5) for the most accurate final transcript.
- All audio is processed in-memory; nothing is written to disk by the service itself.
- CORS is wide open by default (`allow_origins=["*"]`) — restrict it in
  `api/app/main.py` for anything beyond local/internal use.
