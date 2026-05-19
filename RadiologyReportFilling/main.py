"""Main entry point for Medical Imaging Assist."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Handle startup and shutdown lifecycle events."""
    logger.info("Starting %s v%s", settings.api_title, settings.api_version)
    logger.info("Model: %s | Embed model: %s", settings.openai_model, settings.openai_embed_model)
    logger.info("ICD-10 file: %s | RadLex file: %s", settings.icd10_file, settings.radlex_file)
    logger.info("Embeddings cache: %s", settings.rag_embeddings_file)
    logger.info("OpenAI configured: %s", bool(settings.openai_api_key))
    logger.info("Output persistence: %s", settings.persist_output)
    yield
    logger.info("Shutting down Medical Imaging Assist")


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
        "service": "medical-imaging-assist",
        "message": "Medical Imaging Assist is running",
        "version": settings.api_version,
        "model": settings.openai_model,
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
