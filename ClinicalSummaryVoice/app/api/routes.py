"""API routes for ClinicalSummaryVoice."""

import base64

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.config import settings
from app.models.schemas import HealthResponse, SummarizeJsonRequest, SummaryResponse
from app.services.summary_service import summarize_dictation

router = APIRouter(prefix="/api/v1", tags=["clinical-summary-voice"])


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


@router.post("/summarize", response_model=SummaryResponse)
async def summarize(request: Request) -> dict:
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()

    if content_type == "application/json":
        try:
            payload = SummarizeJsonRequest.model_validate(await request.json())
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return summarize_dictation(
            audio_bytes=_decode_audio_base64(payload.audio_base64),
            filename=payload.filename or "audio.wav",
        )

    form = await request.form()
    audio = form.get("audio")
    audio_b64 = _form_str(form.get("audio_base64"))
    if isinstance(audio, StarletteUploadFile):
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="audio file is empty")
        filename = audio.filename or "audio.wav"
    elif audio_b64:
        audio_bytes = _decode_audio_base64(audio_b64)
        filename = _form_str(form.get("filename")) or "audio.wav"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="audio file is required (multipart) or send application/json with audio_base64",
        )

    return summarize_dictation(audio_bytes=audio_bytes, filename=filename)


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok" if settings.openai_api_key or settings.use_llm_stub else "degraded",
        details={
            "service": settings.api_title,
            "version": settings.api_version,
            "summary_model": settings.openai_summary_model,
            "transcribe_model": settings.openai_transcribe_model,
            "stub": settings.use_llm_stub,
        },
    )
