"""REST endpoints for file-based and chunk-based transcription."""
from __future__ import annotations

import logging
import shutil
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse

from app.core.audio_processor import (
    AudioDecodeError,
    FFmpegNotInstalledError,
    decode_to_pcm_f32,
    audio_duration_seconds,
)
from app.core.radiology_postprocess import normalize_radiology_text, normalize_segments
from app.models.schemas import (
    ErrorResponse,
    HealthResponse,
    ServiceInfoResponse,
    TranscriptionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["transcription"])


def _get_engine(request: Request):
    engine = getattr(request.app.state, "whisper_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Whisper model is not loaded yet.")
    return engine


def _get_settings(request: Request):
    return request.app.state.settings


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    engine = getattr(request.app.state, "whisper_engine", None)
    settings = request.app.state.settings
    return HealthResponse(
        status="ok" if engine is not None else "degraded",
        model=getattr(engine, "model_name", settings.whisper_model),
        device=getattr(engine, "device", "unknown"),
        compute_type=getattr(engine, "compute_type", "unknown"),
        radiology_prompt_loaded=bool(getattr(engine, "initial_prompt", None)),
        ffmpeg_available=shutil.which("ffmpeg") is not None,
    )


@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def transcribe_file(
    request: Request,
    file: UploadFile = File(..., description="Audio file (wav/mp3/m4a/webm/ogg/flac)."),
    language: Optional[str] = Form(None, description="Language hint, e.g. 'en'. Defaults to server config."),
    extra_prompt: Optional[str] = Form(None, description="Extra biasing prompt (case/patient context)."),
    beam_size: int = Form(5, ge=1, le=10),
    include_raw_text: bool = Form(False, description="Also return raw (pre-postprocessed) text."),
):
    """Transcribe a complete audio file uploaded as multipart/form-data."""
    settings = _get_settings(request)
    engine = _get_engine(request)
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file upload.")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size ({settings.max_upload_mb} MB).",
        )

    try:
        pcm = decode_to_pcm_f32(raw, input_hint=file.filename)
    except FFmpegNotInstalledError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except AudioDecodeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if audio_duration_seconds(pcm) < 0.1:
        raise HTTPException(status_code=400, detail="Audio is too short to transcribe.")

    try:
        result = engine.transcribe_audio_array(
            pcm, language=language, beam_size=beam_size, extra_prompt=extra_prompt,
        )
    except Exception as e:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=500, detail=f"Transcription error: {e}")

    raw_text = result.text
    fixed_text = normalize_radiology_text(raw_text)
    fixed_segments = normalize_segments([s.to_dict() for s in result.segments])

    payload = TranscriptionResponse(
        request_id=request_id,
        text=fixed_text,
        raw_text=raw_text if include_raw_text else None,
        language=result.language,
        language_probability=result.language_probability,
        audio_duration_seconds=result.duration_audio_s,
        inference_seconds=result.duration_inference_s,
        segments=fixed_segments,
        model=result.model,
        device=result.device,
    )
    return payload


@router.post(
    "/transcribe/chunk",
    response_model=TranscriptionResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def transcribe_chunk(
    request: Request,
    file: UploadFile = File(..., description="A short audio chunk (any container FFmpeg can decode)."),
    language: Optional[str] = Form(None),
    extra_prompt: Optional[str] = Form(None),
):
    """Stateless per-chunk transcription. Suitable for clients that buffer their own audio
    and want a quick transcription of one slice. For real-time streaming use the WebSocket endpoint."""
    settings = _get_settings(request)
    engine = _get_engine(request)
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty chunk.")
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Chunk too large.")

    try:
        pcm = decode_to_pcm_f32(raw, input_hint=file.filename)
    except (FFmpegNotInstalledError, AudioDecodeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    if audio_duration_seconds(pcm) < 0.05:
        return TranscriptionResponse(
            request_id=request_id,
            text="",
            language=settings.whisper_language or "en",
            language_probability=0.0,
            audio_duration_seconds=0.0,
            inference_seconds=0.0,
            segments=[],
            model=engine.model_name,
            device=engine.device,
        )

    result = engine.transcribe_audio_array(
        pcm, language=language, beam_size=1, extra_prompt=extra_prompt,  # beam=1 for speed
    )
    raw_text = result.text
    fixed_text = normalize_radiology_text(raw_text)
    fixed_segments = normalize_segments([s.to_dict() for s in result.segments])

    return TranscriptionResponse(
        request_id=request_id,
        text=fixed_text,
        raw_text=raw_text,
        language=result.language,
        language_probability=result.language_probability,
        audio_duration_seconds=result.duration_audio_s,
        inference_seconds=result.duration_inference_s,
        segments=fixed_segments,
        model=result.model,
        device=result.device,
    )
