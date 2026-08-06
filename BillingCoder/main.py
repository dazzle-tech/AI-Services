"""Main entry point for CodingAssist."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.rag.seeder import seed_rag_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Handle startup and shutdown lifecycle events.

    On startup the RAG store is seeded with code lookups for the common
    diagnosis/procedure terms listed in coding_seed_terms.json. Seeding is
    idempotent: if the persistent store already contains records the seed
    is skipped.
    """
    logger.info("Starting %s v%s", settings.api_title, settings.api_version)
    logger.info("OpenAI model: %s", settings.openai_model)
    logger.info("Embedding model: %s", settings.openai_embedding_model)
    logger.info("RAG persist dir: %s", settings.rag_persist_dir)
    try:
        count = seed_rag_store(force=False)
        logger.info("RAG store ready with %d records.", count)
    except Exception as exc:
        if exc.__class__.__name__ == "AuthenticationError":
            logger.error(
                "RAG seeding failed: invalid OpenAI credentials. "
                "Set a valid OPENAI_API_KEY, or use a local OpenAI-compatible endpoint with "
                "OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL=gpt-4o, and "
                "OPENAI_EMBEDDING_MODEL=text-embedding-3-small."
            )
        else:
            logger.exception("RAG seeding failed: %s", exc)
    yield
    logger.info("Shutting down CodingAssist")


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
        "service": "CodingAssist",
        "message": "AI medical coding & charge-capture service is running",
        "version": settings.api_version,
        "model": settings.openai_model,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import os
    import uvicorn

    port = settings.api_port
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=port,
        reload=settings.api_reload,
        log_level="info",
    )
