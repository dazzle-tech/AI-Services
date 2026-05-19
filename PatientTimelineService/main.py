"""Main entry point for the Patient Timeline Service."""
import logging
import os

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Include routers
app.include_router(router)


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "message": "Patient Timeline Service is running!",
        "version": settings.api_version,
        "model": settings.openai_model,
        "docs": "/docs"
    }


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info(f"Starting {settings.api_title} v{settings.api_version}")
    logger.info(f"Using OpenAI model: {settings.openai_model}")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Shutting down Patient Timeline Service")


if __name__ == "__main__":
    # App Platform uses PORT environment variable
    port = int(os.environ.get("PORT", settings.api_port))

    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower()
    )
