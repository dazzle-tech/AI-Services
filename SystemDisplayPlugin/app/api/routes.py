"""API routes for SystemDisplayPlugin."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.schemas import HealthResponse, ReshapeRequest, ReshapeResponse, ViewDecoder, ViewResult
from app.services.decoder_service import DecoderService
from app.services.mapping_service import AllViewsFailed, reshape_many

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["systemdisplayplugin"])


@router.post("/reshape", response_model=ReshapeResponse)
async def reshape_view(
    body: ReshapeRequest,
    db: Session = Depends(get_db),
) -> ReshapeResponse:
    service = DecoderService(db)
    decoders = list(body.collected_inline_views())
    unresolved: list[ViewResult] = []
    for view_id in body.collected_view_ids():
        decoder = service.get_optional(view_id)
        if decoder is None:
            unresolved.append(
                ViewResult(
                    view_id=view_id,
                    data={},
                    warnings=[f"View decoder '{view_id}' not found"],
                )
            )
        else:
            decoders.append(decoder)

    try:
        result = reshape_many(
            body.stage1_output,
            decoders,
            context=body.context,
            purpose=body.purpose,
            unresolved=unresolved,
        )
    except AllViewsFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"results": [item.model_dump() for item in exc.results]},
        ) from exc
    logger.info(
        "Reshape request completed",
        extra={"view_count": len(result.results), "event_type": "reshape"},
    )
    return result


@router.post("/decoders", response_model=ViewDecoder, status_code=status.HTTP_201_CREATED)
async def register_decoder(
    body: ViewDecoder,
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
    db: Session = Depends(get_db),
) -> ViewDecoder:
    return DecoderService(db).get(view_id)


@router.get("/health", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    db_status = "ok"
    details: Dict[str, Any] = {"service": settings.api_title, "version": settings.api_version}

    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = "error"
        details["database_error"] = str(exc)

    if settings.openai_api_key:
        details["openai_configured"] = True
        details["mapping_model"] = settings.mapping_model

    overall = "ok" if db_status == "ok" else "degraded"
    return HealthResponse(status=overall, database=db_status, details=details)
