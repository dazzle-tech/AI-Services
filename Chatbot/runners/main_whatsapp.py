"""Main entry point for WhatsApp adapter service."""
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path so we can import app
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from app.core.config import settings
from app.api.routes import whatsapp

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | whatsapp_adapter | %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="WhatsApp Adapter Service",
    version="1.0.0",
    description="WhatsApp Business Cloud adapter for MedAI Assistant",
)

# Include router
app.include_router(whatsapp.router)


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "WhatsApp Adapter Service",
        "status": "healthy",
    }


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "WhatsApp Adapter Service",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", settings.whatsapp_adapter_port))
    logger.info("🚀 Starting WhatsApp Adapter on port %s", port)
    uvicorn.run(
        "runners.main_whatsapp:app",
        host=settings.api_host,
        port=port,
        reload=settings.api_reload,
        reload_dirs=[str(Path(__file__).parent.parent / "app"), str(Path(__file__).parent.parent / "runners")] if settings.api_reload else None,
        log_level="info",
    )
