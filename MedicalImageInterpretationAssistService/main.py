from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os

from fastapi import Depends
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import Settings, get_settings
from app.interpretation.xray_model import model_status
from app.main import app

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_app):
    settings = get_settings()
    logger.info(f"Starting Medical Image Interpretation Assist Service ({settings.service_name})")
    yield
    logger.info("Shutting down Medical Image Interpretation Assist Service")


app.router.lifespan_context = _lifespan


@app.get("/")
def root(settings: Settings = Depends(get_settings)):
    return {
        "message": "Medical Image Interpretation Assist Service is running!",
        "service": settings.service_name,
        "version": getattr(app, "version", "unknown"),
        "docs": "/docs",
        "health": "/api/v1/health",
    }


@app.get("/api/v1/health")
def health_v1(settings: Settings = Depends(get_settings)):
    return {"status": "ok", "service": settings.service_name, **model_status(settings.openai_api_key)}


if __name__ == "__main__":
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv()
    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT") or os.environ.get("API_PORT") or "8000")
    reload_enabled = (os.environ.get("API_RELOAD", "false") or "false").lower() in {
        "1",
        "true",
        "yes",
    }
    uvicorn.run(app, host=host, port=port, reload=reload_enabled, log_level="info")
