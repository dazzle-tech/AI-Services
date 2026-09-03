"""API routes for ConvoScribe."""

import base64
import json
import logging
from io import BytesIO

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.auth import AuthContext
from app.core.config import settings
from app.models.schemas import AnalyzeAudioResponse, AnalyzeJsonRequest, TranscriptionRequestOptions, options_from_form
from app.services.pipeline_service import process_audio
from app.services.session_service import SessionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["convoscribe"])


def _prompt_options_from_form(context_type, attendees, purpose, detail_level):
    try:
        return options_from_form(context_type, attendees, purpose, detail_level)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


def _analyze_bytes(
    data: bytes,
    filename: str,
    prompt_options: TranscriptionRequestOptions,
    clinician: AuthContext,
) -> AnalyzeAudioResponse:
    upload = UploadFile(filename=filename, file=BytesIO(data))
    extension = SessionService._validate_upload(upload)
    duration = SessionService._get_duration_seconds(data, extension)

    if duration > settings.max_audio_duration_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio duration {duration:.1f}s exceeds maximum {settings.max_audio_duration_seconds}s",
        )

    result = process_audio(data, f"audio.{extension}", prompt_options=prompt_options)
    logger.info(
        "Audio analyzed synchronously context=%s purpose=%s segments=%s needs_review=%s",
        prompt_options.context_type,
        prompt_options.purpose,
        len(result.raw_transcript.segments),
        result.needs_review,
        extra={
            "clinician_id": clinician.clinician_id if clinician else None,
            "event_type": "analyze",
            "needs_review": result.needs_review,
            "segment_count": len(result.raw_transcript.segments),
        },
    )
    return AnalyzeAudioResponse(
        raw_transcript=result.raw_transcript,
        role_map=result.role_map,
        role_confidence=result.role_confidence,
        role_reasoning=result.role_reasoning,
        needs_review=result.needs_review,
        summary=result.summary,
        narrative_summary=result.narrative_summary,
        clinical_document=result.clinical_document,
    )


@router.post("/analyze", response_model=AnalyzeAudioResponse)
async def analyze_audio(request: Request) -> AnalyzeAudioResponse:
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()

    if content_type == "application/json":
        try:
            payload = AnalyzeJsonRequest.model_validate(await request.json())
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        raw = payload.audio_base64.strip()
        if raw.lower().startswith("data:") and "," in raw:
            raw = raw.split(",", 1)[1]
        try:
            data = base64.b64decode(raw, validate=False)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio_base64 is not valid base64") from exc
        if not data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio_base64 is empty")

        options = TranscriptionRequestOptions(
            context_type=payload.context_type,
            attendees=payload.attendees,
            purpose=payload.purpose,
            detail_level=payload.detail_level,
        )
        return _analyze_bytes(data, payload.filename, options, AuthContext())

    form = await request.form()
    audio = form.get("audio")
    if not isinstance(audio, StarletteUploadFile):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="audio file is required (multipart) or send application/json with audio_base64",
        )
    data = await audio.read()
    prompt_options = _prompt_options_from_form(
        _form_str(form.get("context_type")),
        _form_str(form.get("attendees")),
        _form_str(form.get("purpose")),
        _form_str(form.get("detail_level")),
    )
    return _analyze_bytes(data, audio.filename or "audio.wav", prompt_options, AuthContext())


def _form_str(value) -> str | None:
    if value is None or isinstance(value, StarletteUploadFile):
        return None
    text = str(value).strip()
    return text or None
