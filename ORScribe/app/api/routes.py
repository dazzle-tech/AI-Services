"""API routes for ORScribe."""

import base64
import json
import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from openai import AuthenticationError, APIError
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.auth import assert_case_access, get_staff_context, AuthContext
from app.core.config import settings
from app.db.session import get_db
from app.models.schemas import (
    AnalyzeAudioResponse,
    AnalyzeJsonRequest,
    ApproveRequest,
    AudioChunkResponse,
    CaseCreateResponse,
    CaseResponse,
    ChecklistPhaseResult,
    ChecklistVerificationResult,
    HealthResponse,
    RoleUpdateRequest,
    TranscriptResponse,
    TranscriptionRequestOptions,
    WindowId,
    WindowRole,
    WindowTranscribeResponse,
    options_from_form,
)
from app.services.case_service import CaseService
from app.services.pipeline_service import process_audio
from app.services.window_transcribe_service import transcribe_window_audio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["orscribe"])


def _prompt_options_from_form(context_type, attendees, purpose, detail_level):
    try:
        return options_from_form(context_type, attendees, purpose, detail_level)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


def _form_str(value) -> str | None:
    if value is None or isinstance(value, StarletteUploadFile):
        return None
    text = str(value).strip()
    return text or None


def _decode_audio_base64(raw: str) -> bytes:
    value = raw.strip()
    if value.lower().startswith("data:") and "," in value:
        value = value.split(",", 1)[1]
    try:
        data = base64.b64decode(value, validate=False)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="audio_base64 is not valid base64",
        ) from exc
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio_base64 is empty")
    return data


def _analyze_bytes(
    data: bytes,
    filename: str,
    prompt_options: TranscriptionRequestOptions,
    scheduled_team: dict | None = None,
    procedure_type: str = "",
) -> AnalyzeAudioResponse:
    upload = UploadFile(filename=filename, file=BytesIO(data))
    extension = CaseService._validate_upload(upload)
    duration = CaseService._get_duration_seconds(data, extension)

    if duration > settings.max_audio_duration_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio duration {duration:.1f}s exceeds maximum {settings.max_audio_duration_seconds}s",
        )

    try:
        result = process_audio(
            data,
            f"audio.{extension}",
            scheduled_team=scheduled_team,
            prompt_options=prompt_options,
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OpenAI rejected the API key. Check OPENAI_API_KEY in .env (not a placeholder like sk-...).",
        ) from exc
    except APIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI API error: {exc}",
        ) from exc
    logger.info(
        "Audio analyzed synchronously",
        extra={
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


@router.post("/windows/transcribe", response_model=WindowTranscribeResponse)
async def transcribe_window(
    audio: UploadFile = File(...),
    case_id: str = Form("unspecified"),
    window_id: WindowId = Form(...),
    role: WindowRole = Form(...),
    staff: AuthContext = Depends(get_staff_context),
) -> WindowTranscribeResponse:
    """Stateless single-speaker STT for one UI window. Does not write to the database."""
    resolved_staff_id = ""
    extension = CaseService._validate_upload(audio)
    data = await audio.read()
    duration = CaseService._get_duration_seconds(data, extension)

    if duration > settings.max_audio_duration_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio duration {duration:.1f}s exceeds maximum {settings.max_audio_duration_seconds}s",
        )

    try:
        text = transcribe_window_audio(data, audio.filename or f"audio.{extension}", window_id=window_id)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OpenAI rejected the API key. Check OPENAI_API_KEY in .env (not a placeholder like sk-...).",
        ) from exc
    except APIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI API error: {exc}",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Window transcription failed",
            extra={"case_id": case_id, "window_id": window_id, "event_type": "window_transcribe"},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Transcription failed: {exc}",
        ) from exc

    transcribed_at = datetime.now(timezone.utc)
    logger.info(
        "Window audio transcribed",
        extra={
            "case_id": case_id,
            "window_id": window_id,
            "event_type": "window_transcribe",
            "role": role,
            "duration_seconds": round(duration, 2),
        },
    )
    return WindowTranscribeResponse(
        case_id=case_id,
        window_id=window_id,
        role=role,
        staff_id=resolved_staff_id,
        text=text,
        duration_seconds=duration,
        language="en",
        transcribed_at=transcribed_at,
    )


@router.post("/analyze", response_model=AnalyzeAudioResponse)
async def analyze_audio(request: Request) -> AnalyzeAudioResponse:
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()

    if content_type == "application/json":
        try:
            payload = AnalyzeJsonRequest.model_validate(await request.json())
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        options = TranscriptionRequestOptions(
            context_type=payload.context_type,
            attendees=payload.attendees,
            purpose=payload.purpose,
            detail_level=payload.detail_level,
        )
        return _analyze_bytes(
            _decode_audio_base64(payload.audio_base64),
            payload.filename,
            options,
            scheduled_team=payload.scheduled_team,
            procedure_type=payload.procedure_type,
        )

    form = await request.form()
    audio = form.get("audio")
    if not isinstance(audio, StarletteUploadFile):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="audio file is required (multipart) or send application/json with audio_base64",
        )
    data = await audio.read()
    scheduled_raw = _form_str(form.get("scheduled_team"))
    team = json.loads(scheduled_raw) if scheduled_raw else None
    prompt_options = _prompt_options_from_form(
        _form_str(form.get("context_type")),
        _form_str(form.get("attendees")),
        _form_str(form.get("purpose")),
        _form_str(form.get("detail_level")),
    )
    return _analyze_bytes(
        data,
        audio.filename or "audio.wav",
        prompt_options,
        scheduled_team=team,
        procedure_type=_form_str(form.get("procedure_type")) or "",
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
        staff_id=staff.staff_id or "unspecified",
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
        staff_id=staff.staff_id or "unspecified",
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
    case = service.update_roles(case, body.role_map, staff.staff_id or "unspecified")
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
    case = service.approve_case(case, staff.staff_id or body.user_id)
    return service.to_response(case)


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
        details["role_id_model"] = settings.role_id_model
        details["record_model"] = settings.record_model

    overall = "ok" if db_status == "ok" else "degraded"
    return HealthResponse(status=overall, database=db_status, details=details)
