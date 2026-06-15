"""Main entry point for the OCR Parsing Service."""
import logging
import os
from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
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
async def root() -> dict[str, str]:
    return {
        "message": "OCR Parsing Service is running",
        "version": settings.api_version,
        "docs": "/docs",
    }


@app.on_event("startup")
async def startup_event() -> None:
    logger.info("Starting %s v%s", settings.api_title, settings.api_version)
    logger.info("OCR languages: %s", settings.ocr_languages_list)
    logger.info("Structured extraction model: %s", settings.openai_model)
    logger.info("OpenAI configured: %s", bool(settings.openai_api_key))


@app.on_event("shutdown")
async def shutdown_event() -> None:
    logger.info("Shutting down OCR Parsing Service")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", settings.api_port))
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=port,
        reload=settings.api_reload,
        log_level="info",
    )
