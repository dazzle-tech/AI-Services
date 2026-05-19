"""Main entry point for the Specialist Alert Service."""
import logging
import os

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings


logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(router)


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "message": "Specialist Alert Service is running!",
        "version": settings.api_version,
        "model": settings.openai_model,
        "docs": "/docs",
    }


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info("Starting %s v%s", settings.api_title, settings.api_version)
    logger.info("Using OpenAI model: %s", settings.openai_model)


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Shutting down Specialist Alert Service")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT") or os.environ.get("API_PORT") or settings.api_port)

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )
