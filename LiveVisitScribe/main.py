"""Main entry point for LiveVisitScribe."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    logger.info("Shutting down %s", settings.api_title)


app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
async def root():
    return {
        "message": "LiveVisitScribe is running!",
        "version": settings.api_version,
        "websocket": "/api/v1/live",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, log_level=settings.log_level.lower())
