"""Main entry point for the Radiology QC AI service.

This file matches the convention used by the other services in this repo:
- a top-level `main.py` exporting `app`
- `uvicorn main:app` as the default run target
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os

from fastapi import Depends

from app.config import Settings, get_settings
from app.main import app

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_app):
    settings = get_settings()
    logger.info(f"Starting Radiology QC AI ({settings.service_name})")
    yield
    logger.info("Shutting down Radiology QC AI")


# Prefer lifespan over deprecated on_event hooks.
app.router.lifespan_context = _lifespan


@app.get("/")
def root(settings: Settings = Depends(get_settings)):
    return {
        "message": "Radiology QC AI is running!",
        "service": settings.service_name,
        "version": getattr(app, "version", "unknown"),
        "docs": "/docs",
        "health": "/api/v1/health",
    }


@app.get("/api/v1/health")
def health_v1(settings: Settings = Depends(get_settings)):
    # Keep parity with other services that expose `/api/v1/health`.
    return {"status": "ok", "service": settings.service_name}


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    host = os.environ.get("API_HOST") or settings.api_host
    port = int(os.environ.get("PORT") or os.environ.get("API_PORT") or str(settings.api_port))
    reload_enabled = (
        (os.environ.get("API_RELOAD") or str(settings.api_reload)).lower() in {"1", "true", "yes"}
    )
    log_level = (os.environ.get("LOG_LEVEL") or settings.log_level or "INFO").lower()

    # Pass the app object directly so running `python main.py` doesn't re-import this module.
    uvicorn.run(app, host=host, port=port, reload=reload_enabled, log_level=log_level)
