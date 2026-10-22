"""API routes for ConvoVoiceAgent."""

import base64
import json
import time

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import (
    AnalyzeJsonRequest,
    AnalyzeResponse,
    DownstreamHealth,
    DraftJsonRequest,
    DraftResponse,
    HealthResponse,
    NoteOptions,
    RegenerateRequest,
    RegenerateResponse,
)
from app.services.agent_service import analyze_visit, draft_visit, ping_downstream, regenerate_visit_section

router = APIRouter(prefix="/api/v1", tags=["convovoiceagent"])
logger = get_logger(__name__)

# Same headers ConvoScribe accepts. Optional; nothing here authorizes against a visit.
_AUTH_HEADERS = ("X-API-Key", "X-Clinician-Id")
_NOTE_OPTION_FIELDS = (
    "note_language",
    "instruction_language",
    "specialty",
    "note_length",
    "note_form",
    "suggest_icd10",
    "suggest_orders",
)


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


def _parse_view_ids(raw: str | None, fallback: list[str]) -> list[str]:
    if not raw:
        return fallback
    text = raw.strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="view_ids must be a JSON array of strings",
            ) from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) and item.strip() for item in parsed):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="view_ids must be a JSON array of strings",
            )
        return [item.strip() for item in parsed]
    parts = [item.strip() for item in text.split(",") if item.strip()]
    return parts or fallback


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: Request) -> dict[str, Any]:
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    fallback_views = settings.default_view_id_list

    if content_type == "application/json":
        try:
            payload = AnalyzeJsonRequest.model_validate(await request.json())
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return await analyze_visit(
            audio_bytes=_decode_audio_base64(payload.audio_base64),
            filename=payload.filename or "audio.wav",
            content_type="audio/wav",
            context_type=payload.context_type or settings.default_context_type,
            purpose=payload.purpose or settings.default_purpose,
            detail_level=payload.detail_level or settings.default_detail_level,
            view_ids=payload.view_ids or fallback_views,
        )

    form = await request.form()
    audio = form.get("audio")
    audio_b64 = _form_str(form.get("audio_base64"))
    if isinstance(audio, StarletteUploadFile):
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio file is empty")
        filename = audio.filename or "audio.wav"
        media_type = audio.content_type or "application/octet-stream"
    elif audio_b64:
        audio_bytes = _decode_audio_base64(audio_b64)
        filename = _form_str(form.get("filename")) or "audio.wav"
        media_type = "audio/wav"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="audio file is required (multipart) or send application/json with audio_base64",
        )

    return await analyze_visit(
        audio_bytes=audio_bytes,
        filename=filename,
        content_type=media_type,
        context_type=_form_str(form.get("context_type")) or settings.default_context_type,
        purpose=_form_str(form.get("purpose")) or settings.default_purpose,
        detail_level=_form_str(form.get("detail_level")) or settings.default_detail_level,
        view_ids=_parse_view_ids(_form_str(form.get("view_ids")), fallback_views),
    )


def _auth_headers(request: Request) -> dict[str, str]:
    headers = {}
    for name in _AUTH_HEADERS:
        value = (request.headers.get(name) or "").strip()
        if value:
            headers[name] = value
    return headers


def _note_options_from_form(form) -> NoteOptions:
    values: dict[str, Any] = {}
    for name in _NOTE_OPTION_FIELDS:
        value = _form_str(form.get(name))
        if value:
            values[name] = value
    raw_context = _form_str(form.get("patient_context"))
    if raw_context:
        try:
            values["patient_context"] = json.loads(raw_context)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="patient_context must be a JSON object",
            ) from exc
    try:
        return NoteOptions.model_validate(values)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/draft", response_model=DraftResponse)
async def draft(request: Request) -> DraftResponse:
    started = time.perf_counter()
    auth_headers = _auth_headers(request)
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()

    if content_type == "application/json":
        try:
            payload = DraftJsonRequest.model_validate(await request.json())
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        audio_bytes = _decode_audio_base64(payload.audio_base64)
        filename = payload.filename or "audio.wav"
        media_type = "audio/wav"
        options = NoteOptions.model_validate(payload.model_dump(include=set(NoteOptions.model_fields)))
    else:
        form = await request.form()
        audio = form.get("audio")
        audio_b64 = _form_str(form.get("audio_base64"))
        if isinstance(audio, StarletteUploadFile):
            audio_bytes = await audio.read()
            if not audio_bytes:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio file is empty")
            filename = audio.filename or "audio.wav"
            media_type = audio.content_type or "application/octet-stream"
        elif audio_b64:
            audio_bytes = _decode_audio_base64(audio_b64)
            filename = _form_str(form.get("filename")) or "audio.wav"
            media_type = "audio/wav"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="audio file is required (multipart) or send application/json with audio_base64",
            )
        options = _note_options_from_form(form)

    logger.info(
        "Ambient draft requested",
        extra={
            "event_type": "ambient_draft",
            "clinician_id": auth_headers.get("X-Clinician-Id"),
            "specialty": options.specialty,
        },
    )
    return await draft_visit(
        audio_bytes=audio_bytes,
        filename=filename,
        content_type=media_type,
        options=options,
        auth_headers=auth_headers,
        started=started,
    )


@router.post("/sections/regenerate", response_model=RegenerateResponse)
async def regenerate_section(body: RegenerateRequest, request: Request) -> RegenerateResponse:
    auth_headers = _auth_headers(request)
    logger.info(
        "Ambient section regenerate requested",
        extra={
            "event_type": "ambient_regenerate",
            "clinician_id": auth_headers.get("X-Clinician-Id"),
            "section": body.section,
        },
    )
    return await regenerate_visit_section(
        transcript=body.transcript,
        section=body.section,
        instruction=body.instruction,
        options=NoteOptions.model_validate(body.model_dump(include=set(NoteOptions.model_fields))),
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    downstream = await ping_downstream()
    overall = (
        "ok"
        if downstream["convoscribe"] == "ok" and downstream["system_display_plugin"] == "ok"
        else "degraded"
    )
    return HealthResponse(
        status=overall,
        downstream=DownstreamHealth(
            convoscribe=downstream["convoscribe"],
            system_display_plugin=downstream["system_display_plugin"],
        ),
        details={"service": settings.api_title, "version": settings.api_version},
    )
