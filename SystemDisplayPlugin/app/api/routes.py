"""API routes for SystemDisplayPlugin."""

import logging
from typing import Any, Dict

import redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import AuthContext, verify_api_key
from app.core.config import settings
from app.db.session import get_db
from app.models.schemas import HealthResponse, ReshapeRequest, ReshapeResponse, ViewDecoder
from app.services.decoder_service import DecoderService
from app.services.mapping_service import AllRequiredFieldsFailed, reshape

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["systemdisplayplugin"])


@router.post("/reshape", response_model=ReshapeResponse)
async def reshape_view(
    body: ReshapeRequest,
    _: AuthContext = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> ReshapeResponse:
    # Assumption: if both view_decoder and view_id are sent, the inline decoder wins.
    decoder = body.view_decoder
    if decoder is None:
        decoder = DecoderService(db).get(body.view_id)
    try:
        result = reshape(
            body.stage1_output,
            decoder,
            context=body.context,
            purpose=body.purpose,
        )
    except AllRequiredFieldsFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"view_id": exc.view_id, "warnings": exc.warnings},
        ) from exc
    logger.info(
        "Reshape request completed",
        extra={"view_id": result.view_id, "event_type": "reshape"},
    )
    return result


@router.post("/decoders", response_model=ViewDecoder, status_code=status.HTTP_201_CREATED)
async def register_decoder(
    body: ViewDecoder,
    _: AuthContext = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> ViewDecoder:
    decoder = DecoderService(db).upsert(body)
    logger.info(
        "View decoder registered",
        extra={"view_id": decoder.view_id, "event_type": "decoder_register"},
    )
    return decoder


@router.get("/decoders/{view_id}", response_model=ViewDecoder)
async def get_decoder(
    view_id: str,
    _: AuthContext = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> ViewDecoder:
    return DecoderService(db).get(view_id)


@router.get("/health", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    db_status = "ok"
    redis_status = "ok"
    details: Dict[str, Any] = {"service": settings.api_title, "version": settings.api_version}

    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = "error"
        details["database_error"] = str(exc)

    try:
        client = redis.from_url(settings.redis_url)
        client.ping()
    except Exception as exc:
        redis_status = "error"
        details["redis_error"] = str(exc)

    if settings.openai_api_key:
        details["openai_configured"] = True
        details["mapping_model"] = settings.mapping_model

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return HealthResponse(status=overall, database=db_status, redis=redis_status, details=details)
