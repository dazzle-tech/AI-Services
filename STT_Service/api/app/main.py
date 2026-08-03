"""FastAPI application entrypoint for the radiology STT service."""
from __future__ import annotations

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"



import logging
import shutil
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.core.whisper_engine import WhisperEngine
from app.models.schemas import ServiceInfoResponse
from app.routes import transcribe as transcribe_routes
from app.routes import websocket as websocket_routes

# Load .env from the api/ directory (one level up from this file)
load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("stt")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.load()
    app.state.settings = settings

    if not shutil.which("ffmpeg"):
        logger.warning("FFmpeg not found on PATH — audio decoding endpoints will fail until it is installed.")

    try:
        engine = WhisperEngine(settings)
        app.state.whisper_engine = engine
    except Exception:
        logger.exception("Failed to load Whisper model at startup. The service will run in degraded mode.")
        app.state.whisper_engine = None

    yield
    # Nothing to clean up explicitly; faster-whisper has no close method.


app = FastAPI(
    title="Radiology STT API",
    description=(
        "Specialized Speech-to-Text for radiology. Local Whisper inference with "
        "radiology-domain prompt biasing and term post-processing. Supports file upload, "
        "chunk submission, and real-time WebSocket streaming."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transcribe_routes.router)
app.include_router(websocket_routes.router)


@app.get("/", response_model=ServiceInfoResponse, tags=["meta"])
async def root():
    return ServiceInfoResponse(
        endpoints={
            "health": "GET /api/v1/health",
            "transcribe_file": "POST /api/v1/transcribe (multipart: file)",
            "transcribe_chunk": "POST /api/v1/transcribe/chunk (multipart: file)",
            "stream_ws": "WS /api/v1/ws/transcribe (JSON 'start' control then int16 PCM binary frames)",
        }
    )


if __name__ == "__main__":
    import uvicorn

    settings = Settings.load()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
