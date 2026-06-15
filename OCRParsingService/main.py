"""Main entry point for the OCR Parsing Service."""
import logging
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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


def _sanitize_for_json(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(k): _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(item) for item in value]
    return value


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.warning("Request validation failed for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=422,
        content={"detail": _sanitize_for_json(exc.errors())},
    )


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
