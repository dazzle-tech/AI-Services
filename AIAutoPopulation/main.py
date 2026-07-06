"""Main entry point for the AI Auto-Population Service."""
import logging
import os
from fastapi import FastAPI
from app.core.config import settings
from app.api.routes import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
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


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info(f"Starting {settings.api_title} v{settings.api_version}")
    logger.info(f"Using local model: {settings.openai_model}")
    logger.info(f"Loaded from: {__file__} | pid={os.getpid()}")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Shutting down AI Auto-Population Service")


if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", settings.api_port))
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=port,
        reload=settings.api_reload,
        log_level="info"
    )

