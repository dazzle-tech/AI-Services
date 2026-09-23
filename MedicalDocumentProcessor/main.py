"""Main entry point for the Medical Document Processor service."""
import logging
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Include routers
app.include_router(router)


def _sanitize_for_json(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(k): _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(item) for item in value]
    return value


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.warning("Request validation failed for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=422,
        content={"detail": _sanitize_for_json(exc.errors())},
    )


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "message": "Medical Document Processor Service is running!",
        "version": settings.api_version,
        "model": settings.openai_model,
        "docs": "/docs",
    }


@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info("Starting %s v%s", settings.api_title, settings.api_version)
    logger.info("Using OpenAI model: %s (vision: %s)", settings.openai_model, settings.vision_model)
    logger.info("OCR engine: %s", settings.ocr_engine)
    logger.info("Relevance windows (days): %s", settings.relevance_windows_days)


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Shutting down Medical Document Processor Service")


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
