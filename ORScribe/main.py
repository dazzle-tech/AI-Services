"""Main entry point for ORScribe."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as exc:
        logger.warning(
            "Database unavailable at startup (%s). "
            "Start infra with: docker compose up postgres minio -d",
            exc,
        )
    logger.info("Starting %s v%s", settings.api_title, settings.api_version)
    logger.info("Listening on http://%s:%s", settings.api_host, settings.api_port)
    logger.info("Role ID model: %s | Record model: %s", settings.role_id_model, settings.record_model)
    backend = settings.transcription_backend.lower()
    if backend == "stub":
        logger.warning(
            "TRANSCRIPTION_BACKEND=stub — audio content is ignored; "
            "per-window STT returns fixed sample text. "
            "Set TRANSCRIPTION_BACKEND=openai for gpt-4o-transcribe."
        )
    elif backend in {"openai", "openai_transcribe", "gpt-4o-transcribe"}:
        logger.info(
            "Transcription backend: openai (%s)",
            settings.openai_transcribe_model,
        )
        if not settings.openai_api_key or len(settings.openai_api_key) <= 20:
            logger.warning(
                "OPENAI_API_KEY missing or placeholder — openai STT will fail with 401"
            )
    elif backend in {"whisper", "whisper_only"}:
        logger.info("Transcription backend: whisper (%s)", settings.whisper_model_size)
    elif backend == "whisper_pyannote":
        logger.info("Transcription backend: whisper_pyannote (%s)", settings.whisper_model_size)
    if settings.use_llm_stub:
        logger.warning("USE_LLM_STUB=true — role/timeline/checklist use offline stubs, not OpenAI")
    elif settings.openai_api_key and len(settings.openai_api_key) > 20:
        logger.info("OpenAI configured (base_url=%s)", settings.openai_base_url or "default")
    else:
        logger.warning("OPENAI_API_KEY missing or placeholder — LLM calls will fail with 401")
    yield
    logger.info("Shutting down %s", settings.api_title)


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "message": "ORScribe is running!",
        "version": settings.api_version,
        "role_id_model": settings.role_id_model,
        "record_model": settings.record_model,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", settings.api_port))
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=port,
        reload=settings.api_reload,
        log_level="info",
    )
