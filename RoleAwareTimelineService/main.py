"""Main entry point for the Role-Aware Timeline Service."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Log the configured model when the process starts and stops."""
    logger.info("Starting %s v%s", settings.api_title, settings.api_version)
    logger.info("Using OpenAI model: %s", settings.openai_model)
    yield
    logger.info("Shutting down Role-Aware Timeline Service")


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
        "message": "Role-Aware Timeline Service is running.",
        "version": settings.api_version,
        "model": settings.openai_model,
        "docs": "/docs",
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", settings.api_port))

    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )
