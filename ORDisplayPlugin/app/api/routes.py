"""API routes for ORDisplayPlugin."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from openai import APIError, AuthenticationError
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.window_registry import resolve_window_id, role_for_window_id
from app.db.session import get_db
from app.models.schemas import (
    HealthResponse,
    ReshapeRequest,
    ReshapeResponse,
    ViewDecoder,
    ViewResult,
    WindowDispatchRequest,
    WindowExtractRequest,
    WindowExtractResponse,
)
from app.services.decoder_service import DecoderService
from app.services.mapping_service import AllViewsFailed, reshape_many
from app.services.orscribe_adapter import normalize_orscribe_output
from app.services.window_extraction_service import extract_window_fields
from app.models.window_schemas import (
    NursingIntraoperativeFields,
    NursingSignOutFields,
    NursingTimeOutFields,
    OperativeNoteFields,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ordisplayplugin"])


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
            normalize_orscribe_output(body.stage1_output),
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


def _fill_window(window_id: str, body: WindowExtractRequest) -> WindowExtractResponse:
    try:
        return extract_window_fields(
            window_id,
            body.text,
            body.existing_fields,
            case_id=body.case_id,
            role=body.role,
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenAI rejected the API key. Check OPENAI_API_KEY in ORDisplayPlugin .env "
            "(do not prefix the value with OPENAI_API_KEY=).",
        ) from exc
    except APIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI API error: {exc}",
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc


@router.post("/windows/extract", response_model=WindowExtractResponse)
async def extract_by_window_name(body: WindowDispatchRequest) -> WindowExtractResponse:
    """Route by window_name + role onto one of the eight window schemas."""
    window_id = resolve_window_id(body.role, body.window_name)
    return _fill_window(
        window_id,
        WindowExtractRequest(
            text=body.text,
            role=role_for_window_id(window_id, body.role),  # type: ignore[arg-type]
            case_id=body.case_id,
            staff_id=body.staff_id,
            existing_fields=body.existing_fields,
        ),
    )


@router.post("/windows/nursing/verification-of-marking-site", response_model=WindowExtractResponse)
async def fill_nursing_verification_of_marking_site(body: WindowExtractRequest) -> WindowExtractResponse:
    return _fill_window("nursing_verification_of_marking_site", body)


@router.post("/windows/nursing/time-out", response_model=NursingTimeOutFields)
async def fill_nursing_time_out(body: WindowExtractRequest) -> NursingTimeOutFields:
    result = _fill_window("nursing_time_out", body)
    return NursingTimeOutFields.model_validate(result.fields)


@router.post("/windows/nursing/intraoperative", response_model=NursingIntraoperativeFields)
async def fill_nursing_intraoperative(body: WindowExtractRequest) -> NursingIntraoperativeFields:
    result = _fill_window("nursing_intraoperative", body)
    return NursingIntraoperativeFields.model_validate(result.fields)


@router.post("/windows/nursing/sign-out", response_model=NursingSignOutFields)
async def fill_nursing_sign_out(body: WindowExtractRequest) -> NursingSignOutFields:
    result = _fill_window("nursing_sign_out", body)
    return NursingSignOutFields.model_validate(result.fields)


@router.post("/windows/anesthesia/pre-evaluation-plan", response_model=WindowExtractResponse)
async def fill_anesthesia_pre_evaluation_plan(body: WindowExtractRequest) -> WindowExtractResponse:
    return _fill_window("anesthesia_pre_evaluation_plan", body)


@router.post("/windows/anesthesia/induction-intraoperative", response_model=WindowExtractResponse)
async def fill_anesthesia_induction_intraoperative(body: WindowExtractRequest) -> WindowExtractResponse:
    return _fill_window("anesthesia_induction_intraoperative", body)


@router.post("/windows/anesthesia/observation-drugs", response_model=WindowExtractResponse)
async def fill_anesthesia_observation_drugs(body: WindowExtractRequest) -> WindowExtractResponse:
    return _fill_window("anesthesia_observation_drugs", body)


@router.post("/windows/operative-note", response_model=OperativeNoteFields)
async def fill_operative_note(body: WindowExtractRequest) -> OperativeNoteFields:
    result = _fill_window("operative_note", body)
    return OperativeNoteFields.model_validate(result.fields)


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
