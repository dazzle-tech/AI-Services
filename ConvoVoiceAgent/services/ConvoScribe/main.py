"""Main entry point for ConvoScribe."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

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
        logger.warning("Database unavailable at startup (%s).", exc)
    logger.info("Starting %s v%s", settings.api_title, settings.api_version)
    logger.info("Listening on http://%s:%s", settings.api_host, settings.api_port)
    logger.info(
        "Role ID model: %s | Summary model: %s",
        settings.role_id_model,
        settings.summary_model,
    )
    logger.info("Transcription backend: %s", settings.transcription_backend)
    if settings.transcription_backend.lower() in {"whisper_pyannote"} and not settings.pyannote_hf_token:
        logger.warning(
            "PYANNOTE_HF_TOKEN is not set — whisper_pyannote diarization will fail. "
            "Use TRANSCRIPTION_BACKEND=whisper for real ASR without a Hugging Face token."
        )
    if settings.use_llm_stub:
        logger.warning("USE_LLM_STUB=true — role ID and summary use offline stubs, not OpenAI")
    elif settings.openai_api_key:
        logger.info("OpenAI configured (base_url=%s)", settings.openai_base_url or "default")
    else:
        logger.warning("OPENAI_API_KEY not set — LLM steps will fail unless USE_LLM_STUB=true")
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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    client = request.client.host if request.client else "unknown"
    logger.info(
        "Request %s %s from %s",
        request.method,
        request.url.path,
        client,
        extra={"event_type": "http"},
    )
    response = await call_next(request)
    if response.status_code >= 400:
        logger.warning(
            "Response %s %s from %s -> %s",
            request.method,
            request.url.path,
            client,
            response.status_code,
            extra={"event_type": "http"},
        )
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level="info",
    )
