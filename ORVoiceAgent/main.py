"""Main entry point for ORVoiceAgent."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.core.logging import configure_logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("Starting %s v%s", settings.api_title, settings.api_version)
    logger.info("Listening on http://%s:%s", settings.api_host, settings.api_port)
    logger.info("ORScribe: %s", settings.orscribe_base_url)
    logger.info("ORDisplayPlugin: %s", settings.ordisplay_base_url)
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
    return {
        "message": "ORVoiceAgent is running!",
        "version": settings.api_version,
        "orscribe": settings.orscribe_base_url,
        "ordisplay_plugin": settings.ordisplay_base_url,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level="info",
    )
