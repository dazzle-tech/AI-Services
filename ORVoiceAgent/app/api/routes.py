"""API routes for ORVoiceAgent — same window paths as ORDisplayPlugin."""

import base64

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.config import settings
from app.core.window_registry import WindowSpec
from app.models.schemas import (
    AgentWindowJsonRequest,
    DownstreamHealth,
    HealthResponse,
    IntraoperativeResponse,
    OperativeNoteResponse,
    SignOutResponse,
    TimeOutResponse,
    WindowExtractResponse,
)
from app.services.agent_service import fill_window, ping_downstream, spec_for

router = APIRouter(prefix="/api/v1", tags=["orvoiceagent"])


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


async def _handle_window_voice(
    request: Request,
    spec: WindowSpec,
) -> dict[str, Any]:
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()

    if content_type == "application/json":
        try:
            payload = AgentWindowJsonRequest.model_validate(await request.json())
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        return await fill_window(
            spec,
            audio_bytes=_decode_audio_base64(payload.audio_base64),
            filename=payload.filename or "audio.wav",
            content_type="audio/wav",
            role=payload.role,
        )

    form = await request.form()
    audio = form.get("audio")
    audio_b64 = _form_str(form.get("audio_base64"))
    if isinstance(audio, StarletteUploadFile):
        audio_bytes = await audio.read()
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

    return await fill_window(
        spec,
        audio_bytes=audio_bytes,
        filename=filename,
        content_type=media_type,
        role=_form_str(form.get("role")),
    )


@router.post("/windows/nursing/verification-of-marking-site", response_model=WindowExtractResponse)
async def fill_nursing_verification_of_marking_site(
    request: Request,
) -> WindowExtractResponse:
    return await _handle_window_voice(request, spec_for("nursing_verification_of_marking_site"))


@router.post("/windows/nursing/time-out", response_model=TimeOutResponse)
async def fill_nursing_time_out(
    request: Request,
) -> dict[str, Any]:
    return await _handle_window_voice(request, spec_for("nursing_time_out"))


@router.post("/windows/nursing/intraoperative", response_model=IntraoperativeResponse)
async def fill_nursing_intraoperative(
    request: Request,
) -> dict[str, Any]:
    return await _handle_window_voice(request, spec_for("nursing_intraoperative"))


@router.post("/windows/nursing/sign-out", response_model=SignOutResponse)
async def fill_nursing_sign_out(
    request: Request,
) -> dict[str, Any]:
    return await _handle_window_voice(request, spec_for("nursing_sign_out"))


@router.post("/windows/anesthesia/pre-evaluation-plan", response_model=WindowExtractResponse)
async def fill_anesthesia_pre_evaluation_plan(
    request: Request,
) -> WindowExtractResponse:
    return await _handle_window_voice(request, spec_for("anesthesia_pre_evaluation_plan"))


@router.post("/windows/anesthesia/induction-intraoperative", response_model=WindowExtractResponse)
async def fill_anesthesia_induction_intraoperative(
    request: Request,
) -> WindowExtractResponse:
    return await _handle_window_voice(request, spec_for("anesthesia_induction_intraoperative"))


@router.post("/windows/anesthesia/observation-drugs", response_model=WindowExtractResponse)
async def fill_anesthesia_observation_drugs(
    request: Request,
) -> WindowExtractResponse:
    return await _handle_window_voice(request, spec_for("anesthesia_observation_drugs"))


@router.post("/windows/operative-note", response_model=OperativeNoteResponse)
async def fill_operative_note(
    request: Request,
) -> dict[str, Any]:
    return await _handle_window_voice(request, spec_for("operative_note"))


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    downstream = await ping_downstream()
    overall = (
        "ok"
        if downstream["orscribe"] == "ok" and downstream["ordisplay_plugin"] == "ok"
        else "degraded"
    )
    return HealthResponse(
        status=overall,
        downstream=DownstreamHealth(
            orscribe=downstream["orscribe"],
            ordisplay_plugin=downstream["ordisplay_plugin"],
        ),
        details={"service": settings.api_title, "version": settings.api_version},
    )
