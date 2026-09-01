"""API routes for ORScribe."""

import json
import logging
from typing import Any, Dict
from uuid import UUID

import redis
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import assert_case_access, get_staff_context, AuthContext
from app.core.config import settings
from app.db.session import get_db
from app.models.schemas import (
    AnalyzeAudioResponse,
    ApproveRequest,
    AudioChunkResponse,
    CaseCreateResponse,
    CaseResponse,
    ChecklistPhaseResult,
    ChecklistVerificationResult,
    HealthResponse,
    RoleUpdateRequest,
    TranscriptResponse,
    options_from_form,
)
from app.services.case_service import CaseService
from app.services.pipeline_service import process_audio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["orscribe"])


def _prompt_options_from_form(context_type, attendees, purpose, detail_level):
    try:
        return options_from_form(context_type, attendees, purpose, detail_level)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/analyze", response_model=AnalyzeAudioResponse)
async def analyze_audio(
    audio: UploadFile = File(...),
    procedure_type: str = Form(""),
    scheduled_team: str | None = Form(None),
    context_type: str | None = Form(None),
    attendees: str | None = Form(None),
    purpose: str | None = Form(None),
    detail_level: str | None = Form(None),
    staff: AuthContext = Depends(get_staff_context),
) -> AnalyzeAudioResponse:
    extension = CaseService._validate_upload(audio)
    data = audio.file.read()
    duration = CaseService._get_duration_seconds(data, extension)

    if duration > settings.max_audio_duration_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio duration {duration:.1f}s exceeds maximum {settings.max_audio_duration_seconds}s",
        )

    team = json.loads(scheduled_team) if scheduled_team else None
    prompt_options = _prompt_options_from_form(context_type, attendees, purpose, detail_level)
    filename = f"audio.{extension}"
    result = process_audio(data, filename, scheduled_team=team, prompt_options=prompt_options)
    logger.info(
        "Audio analyzed synchronously",
        extra={
            "staff_id": staff.staff_id,
            "case_id": "-",
            "event_type": "analyze",
            "procedure_type": procedure_type or None,
            "needs_review": result.needs_review,
            "segment_count": len(result.raw_transcript.segments),
        },
    )
    return AnalyzeAudioResponse(
        raw_transcript=result.raw_transcript,
        role_map=result.role_map,
        role_reasoning=result.role_reasoning,
        needs_review=result.needs_review,
        timeline=result.timeline,
        checklist=result.checklist,
    )


@router.post("/cases", response_model=CaseCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_case(
    procedure_type: str = Form(...),
    ingest_mode: str = Form("post_hoc"),
    scheduled_team: str | None = Form(None),
    context_type: str | None = Form(None),
    attendees: str | None = Form(None),
    purpose: str | None = Form(None),
    detail_level: str | None = Form(None),
    audio: UploadFile | None = File(None),
    staff: AuthContext = Depends(get_staff_context),
    db: Session = Depends(get_db),
) -> CaseCreateResponse:
    team = json.loads(scheduled_team) if scheduled_team else None
    prompt_options = _prompt_options_from_form(context_type, attendees, purpose, detail_level)
    service = CaseService(db)
    case = service.create_case(
        procedure_type=procedure_type,
        staff_id=staff.staff_id,
        scheduled_team=team,
        ingest_mode=ingest_mode,
        audio=audio,
        prompt_options=prompt_options,
    )
    return CaseCreateResponse(case_id=case.id, status=case.status.value)


@router.post(
    "/cases/{case_id}/audio-chunk",
    response_model=AudioChunkResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_audio_chunk(
    case_id: UUID,
    chunk_index: int = Form(...),
    is_final: bool = Form(False),
    audio: UploadFile = File(...),
    staff: AuthContext = Depends(get_staff_context),
    db: Session = Depends(get_db),
) -> AudioChunkResponse:
    service = CaseService(db)
    case = service.get_case(case_id)
    assert_case_access(case, staff.staff_id)
    chunk = service.add_audio_chunk(
        case=case,
        audio=audio,
        chunk_index=chunk_index,
        is_final=is_final,
        staff_id=staff.staff_id,
    )
    return AudioChunkResponse(chunk_index=chunk.chunk_index, status=chunk.status.value)


@router.get("/cases/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: UUID,
    staff: AuthContext = Depends(get_staff_context),
    db: Session = Depends(get_db),
) -> CaseResponse:
    service = CaseService(db)
    case = service.get_case(case_id)
    assert_case_access(case, staff.staff_id)
    return service.to_response(case)


@router.get("/cases/{case_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(
    case_id: UUID,
    staff: AuthContext = Depends(get_staff_context),
    db: Session = Depends(get_db),
) -> TranscriptResponse:
    service = CaseService(db)
    case = service.get_case(case_id)
    assert_case_access(case, staff.staff_id)
    if not case.raw_transcript:
        return TranscriptResponse(case_id=case_id, raw_transcript={"segments": []})
    return TranscriptResponse(case_id=case_id, raw_transcript=case.raw_transcript)


@router.patch("/cases/{case_id}/roles", response_model=CaseResponse)
async def update_roles(
    case_id: UUID,
    body: RoleUpdateRequest,
    staff: AuthContext = Depends(get_staff_context),
    db: Session = Depends(get_db),
) -> CaseResponse:
    service = CaseService(db)
    case = service.get_case(case_id)
    assert_case_access(case, staff.staff_id)
    case = service.update_roles(case, body.role_map, staff.staff_id)
    return service.to_response(case)


@router.get("/cases/{case_id}/checklist", response_model=ChecklistVerificationResult)
async def get_checklist(
    case_id: UUID,
    staff: AuthContext = Depends(get_staff_context),
    db: Session = Depends(get_db),
) -> ChecklistVerificationResult:
    service = CaseService(db)
    case = service.get_case(case_id)
    assert_case_access(case, staff.staff_id)
    if not case.checklist_result:
        empty = ChecklistPhaseResult(completed=False, items_confirmed=[], items_missing=[])
        return ChecklistVerificationResult(sign_in=empty, time_out=empty, sign_out=empty)
    return ChecklistVerificationResult.model_validate(case.checklist_result)


@router.post("/cases/{case_id}/approve", response_model=CaseResponse)
async def approve_case(
    case_id: UUID,
    body: ApproveRequest,
    staff: AuthContext = Depends(get_staff_context),
    db: Session = Depends(get_db),
) -> CaseResponse:
    service = CaseService(db)
    case = service.get_case(case_id)
    assert_case_access(case, staff.staff_id)
    if body.user_id != staff.staff_id:
        raise HTTPException(status_code=403, detail="User ID mismatch")
    case = service.approve_case(case, staff.staff_id)
    return service.to_response(case)


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
        details["role_id_model"] = settings.role_id_model
        details["record_model"] = settings.record_model

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return HealthResponse(status=overall, database=db_status, redis=redis_status, details=details)
