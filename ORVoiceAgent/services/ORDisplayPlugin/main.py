"""Main entry point for ORDisplayPlugin."""

import logging
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
        from app.db.session import SessionLocal
        from app.fixtures.decoders import seed_default_decoders

        if SessionLocal is not None:
            db = SessionLocal()
            try:
                seed_default_decoders(db)
                logger.info("Seeded default view decoders")
            finally:
                db.close()
        logger.info("Database initialized")
    except Exception as exc:
        logger.warning(
            "Database unavailable at startup (%s). "
            "POST /api/v1/reshape with an inline view_decoder still works if the "
            "process can open a DB session; stored-decoder endpoints need Postgres. "
            "Start infra with: docker compose up postgres -d",
            exc,
        )
    logger.info("Starting %s v%s", settings.api_title, settings.api_version)
    logger.info("Listening on http://%s:%s", settings.api_host, settings.api_port)
    logger.info("Mapping model: %s", settings.mapping_model)
    if settings.use_llm_stub:
        logger.warning("USE_LLM_STUB=true — non-direct transforms use offline stubs, not OpenAI")
    elif settings.openai_api_key:
        logger.info("OpenAI configured (base_url=%s)", settings.openai_base_url or "default")
    else:
        logger.warning("OPENAI_API_KEY not set — LLM transforms will fail unless USE_LLM_STUB=true")
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
        "message": "ORDisplayPlugin is running!",
        "version": settings.api_version,
        "mapping_model": settings.mapping_model,
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
