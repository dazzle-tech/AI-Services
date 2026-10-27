"""Main entry point for LiveVisitScribe."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.asr import build_transcriber
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("Starting %s v%s", settings.api_title, settings.api_version)
    app.state.transcriber = await asyncio.to_thread(build_transcriber, settings)
    mode = getattr(app.state.transcriber, "name", "unavailable")
    logger.info("Speech: %s | Listening on http://%s:%s (ws path /api/v1/live)", mode, settings.host, settings.port)
    yield
    closer = getattr(app.state.transcriber, "close", None)
    if callable(closer):
        await asyncio.to_thread(closer)
    logger.info("Shutting down %s", settings.api_title)


_dev_pages = settings.enable_dev_pages
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    docs_url="/docs" if _dev_pages else None,
    redoc_url="/redoc" if _dev_pages else None,
    openapi_url="/openapi.json" if _dev_pages else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(router)


_STATIC_DIR = Path(__file__).resolve().parent / "app" / "static"
_TRY_PAGE = _STATIC_DIR / "try.html"

if settings.enable_dev_pages:
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
async def root():
    body = {
        "message": "LiveVisitScribe is running!",
        "version": settings.api_version,
        "websocket": "/api/v1/live",
        "health": "/api/v1/health",
        "ready": "/api/v1/ready",
        "metrics": "/api/v1/metrics",
    }
    if settings.enable_dev_pages:
        body["try"] = "/try"
        body["docs"] = "/docs"
        body["sample_wav"] = "/static/samples/doctor_patient_visit_3min.wav"
    return body


@app.get("/try")
async def try_page():
    """Browser page that opens the live socket and shows lines plus the picked-up list."""
    if not settings.enable_dev_pages:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(_TRY_PAGE)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        ws_max_size=settings.max_frame_bytes,
        timeout_graceful_shutdown=10,
    )
