"""Main entry point for the Clinical Recommendations Service."""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.api.routes import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    # Startup
    logger.info(f"Starting {settings.api_title} v{settings.api_version}")
    logger.info(f"Using OpenAI model: {settings.openai_model}")
    yield
    # Shutdown
    logger.info("Shutting down Clinical Recommendations Service")


# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Include routers
app.include_router(router)


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "message": "Clinical Recommendations Service is running!",
        "version": settings.api_version,
        "model": settings.openai_model,
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    
    # App Platform uses PORT environment variable
    port = int(os.environ.get("PORT", settings.api_port))
    
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=port,
        reload=settings.api_reload,
        log_level="info"
    )

