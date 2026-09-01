"""Main entry point for SystemDisplayPlugin."""

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
            "POST /api/v1/reshape with an inline view_decoder still works if the "
            "process can open a DB session; stored-decoder endpoints need Postgres. "
            "Start infra with: docker compose up postgres redis -d",
            exc,
        )
    logger.info("Starting %s v%s", settings.api_title, settings.api_version)
    logger.info("Mapping model: %s", settings.mapping_model)
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
        "message": "SystemDisplayPlugin is running!",
        "version": settings.api_version,
        "mapping_model": settings.mapping_model,
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
