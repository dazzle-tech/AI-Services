from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os

from fastapi import Depends
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import Settings, get_settings
from app.model_resolver import model_supports_vision
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
    selected_vision_model = settings.vision_model.strip() or "<unset>"
    supports_vision = model_supports_vision(settings.vision_model) if settings.vision_model.strip() else None
    logger.info(
        "Image interpretation startup config ENABLE_IMAGE_MODEL=%s VISION_MODEL=%s supports_vision=%s OPENAI_BASE_URL=%s",
        settings.enable_image_model,
        selected_vision_model,
        supports_vision,
        settings.openai_base_url or "<default>",
    )
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
    settings = get_settings()
    host = os.environ.get("API_HOST", settings.api_host)
    port = int(os.environ.get("PORT") or os.environ.get("API_PORT") or str(settings.api_port))
    reload_enabled = (os.environ.get("API_RELOAD", str(settings.api_reload)) or "false").lower() in {
        "1",
        "true",
        "yes",
    }
    uvicorn.run(app, host=host, port=port, reload=reload_enabled, log_level=settings.log_level.lower())
