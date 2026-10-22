"""Pipeline: ConvoScribe analyze, then SystemDisplayPlugin reshape.

/analyze returns the display JSON. /draft adds the ambient note between the two calls, and
/sections/regenerate redrafts the visit from a transcript the caller already has.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.ai.note_model import ensure_configured
from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import (
    DraftResponse,
    DraftSections,
    NoteOptions,
    TranscriptItem,
)
from app.services import ambient_draft
from app.services.local_services import CONVOSCRIBE_PROBE_PATH

logger = get_logger(__name__)

_RETRY_BACKOFF_SECONDS = 0.25
_SOAP_KEYS = ("subjective", "objective", "assessment", "plan")
# Transcript and speaker roles only: the ambient note model is the single summary step for /draft.
DRAFT_TRANSCRIPT_PURPOSE = "transcript_only"


async def analyze_visit(
    *,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    context_type: str,
    purpose: str,
    detail_level: str,
    view_ids: list[str],
) -> dict[str, Any]:
    timeout = httpx.Timeout(settings.http_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        analyzed = await _analyze(
            client,
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
            context_type=context_type,
            purpose=purpose,
            detail_level=detail_level,
        )
        return await _reshape(
            client,
            stage1_output=stage1_output_from_analyze(analyzed),
            context_type=context_type,
            purpose=purpose,
            view_ids=view_ids,
        )


async def draft_visit(
    *,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    options: NoteOptions,
    auth_headers: dict[str, str],
    started: float,
) -> DraftResponse:
    ensure_configured()
    timeout = httpx.Timeout(settings.http_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        analyzed = await _analyze(
            client,
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
            context_type=settings.default_context_type,
            purpose=DRAFT_TRANSCRIPT_PURPOSE,
            detail_level=settings.default_detail_level,
            headers=auth_headers,
        )
        transcript = ambient_draft.build_transcript(analyzed)
        parts = await ambient_draft.generate_draft(transcript, options)
        soap_note = await _reshape_soap_note(client, parts.sections, ambient_draft.SOAP_NOTE_FIELDS, options)

    record = ambient_draft.record_for_draft(parts, options)
    return DraftResponse(
        transcript=transcript,
        sections=DraftSections(**{name: {"sentences": items} for name, items in parts.sections.items()}),
        soap_note=soap_note,
        diagnoses=parts.diagnoses,
        orders=parts.orders,
        mentions=parts.mentions,
        instructions=parts.instructions,
        flags=parts.flags,
        possible_transcription_errors=parts.transcription_errors,
        patient_context_used=ambient_draft.patient_context_used(options.patient_context),
        record=record.record,
        record_evidence=record.evidence,
        record_status=record.status,
        missing_required=record.missing_required,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )


async def regenerate_visit_section(
    *,
    transcript: list[TranscriptItem],
    section: str,
    instruction: str,
    options: NoteOptions,
    started: float,
) -> DraftResponse:
    parts = await ambient_draft.regenerate_section(transcript, options, section, instruction)
    timeout = httpx.Timeout(settings.http_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        soap_note = await _reshape_soap_note(client, parts.sections, ambient_draft.SOAP_NOTE_FIELDS, options)
    record = ambient_draft.record_for_draft(parts, options)
    return DraftResponse(
        transcript=transcript,
        sections=DraftSections(**{name: {"sentences": items} for name, items in parts.sections.items()}),
        soap_note=soap_note,
        diagnoses=parts.diagnoses,
        orders=parts.orders,
        mentions=parts.mentions,
        instructions=parts.instructions,
        flags=parts.flags,
        possible_transcription_errors=parts.transcription_errors,
        patient_context_used=ambient_draft.patient_context_used(options.patient_context),
        record=record.record,
        record_evidence=record.evidence,
        record_status=record.status,
        missing_required=record.missing_required,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
    )


async def _reshape_soap_note(
    client: httpx.AsyncClient,
    sections: dict[str, list],
    field_names: tuple[str, ...],
    options: NoteOptions,
) -> dict[str, Any]:
    source = ambient_draft.soap_source(sections, note_form=options.note_form, note_language=options.note_language)
    reshaped = await _reshape(
        client,
        stage1_output=source,
        context_type=settings.default_context_type,
        purpose=settings.default_purpose,
        views=[ambient_draft.soap_note_decoder(field_names)],
    )
    results = reshaped.get("results") if isinstance(reshaped.get("results"), list) else []
    data = next(
        (item.get("data") for item in results if isinstance(item, dict) and item.get("view_id") == "soap_note"),
        None,
    )
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SystemDisplayPlugin reshape returned no soap_note view",
        )
    return {name: data.get(name) for name in field_names}


def stage1_output_from_analyze(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten ConvoScribe's clinical object so DisplayPlugin source paths match."""
    flat = _flatten_clinical_output(payload)
    if flat and not isinstance(flat.get("chart"), dict):
        flat["chart"] = _chart_from_soap(flat)
    return flat


def _chart_from_soap(flat: dict[str, Any]) -> dict[str, str]:
    """Older ConvoScribe output has no `chart`; map the four SOAP strings onto chart fields."""

    def stated(key: str) -> str:
        value = flat.get(key)
        if not isinstance(value, str) or value.strip().lower() in {"", "not discussed"}:
            return ""
        return value.strip()

    plan = stated("plan")
    follow_up = stated("follow_up")
    if follow_up and follow_up not in plan:
        plan = f"{plan} Follow-up: {follow_up}".strip()
    return {
        "HPI": stated("subjective"),
        "PhysicalExamination": stated("objective"),
        "Assessments": stated("assessment"),
        "TreatmentPlans": plan,
    }


def _flatten_clinical_output(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    if isinstance(summary, dict) and any(summary.get(key) for key in _SOAP_KEYS):
        return dict(summary)

    narrative = payload.get("narrative_summary")
    if isinstance(narrative, dict) and narrative.get("summary"):
        return {
            "subjective": narrative.get("summary") or "",
            "objective": "",
            "assessment": "",
            "plan": narrative.get("follow_up") or "",
        }

    document = payload.get("clinical_document")
    if isinstance(document, dict):
        sections = document.get("sections") if isinstance(document.get("sections"), dict) else {}
        return {
            "subjective": sections.get("subjective") or document.get("body") or "",
            "objective": sections.get("objective") or "",
            "assessment": sections.get("assessment") or "",
            "plan": sections.get("plan") or "",
        }
    return {}


async def ping_downstream() -> dict[str, str]:
    timeout = httpx.Timeout(5.0)
    result = {"convoscribe": "error", "system_display_plugin": "error"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        result["convoscribe"] = await _ping(client, settings.convoscribe_base_url, CONVOSCRIBE_PROBE_PATH)
        result["system_display_plugin"] = await _ping(client, settings.system_display_base_url)
    return result


async def _ping(client: httpx.AsyncClient, base_url: str, path: str = "/api/v1/health") -> str:
    try:
        response = await client.get(f"{base_url.rstrip('/')}{path}")
    except httpx.HTTPError as exc:
        return f"unreachable: {exc.__class__.__name__}"
    return "ok" if response.status_code == 200 else f"http_{response.status_code}"


async def _analyze(
    client: httpx.AsyncClient,
    *,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    context_type: str,
    purpose: str,
    detail_level: str,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    url = f"{settings.convoscribe_base_url.rstrip('/')}/api/v1/analyze"
    data = {
        "context_type": context_type,
        "purpose": purpose,
        "detail_level": detail_level,
    }
    files = {"audio": (filename, audio_bytes, content_type)}
    started = time.perf_counter()
    response = await _request_with_retry(client, "POST", url, data=data, files=files, headers=headers or None)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "ConvoScribe analyze completed",
        extra={"event_type": "agent_analyze", "elapsed_ms": elapsed_ms, "status_code": response.status_code},
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ConvoScribe analyze failed: {response.status_code} {response.text}",
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ConvoScribe analyze returned a non-object body",
        )
    return payload


async def _reshape(
    client: httpx.AsyncClient,
    *,
    stage1_output: dict[str, Any],
    context_type: str,
    purpose: str,
    view_ids: list[str] | None = None,
    views: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    url = f"{settings.system_display_base_url.rstrip('/')}/api/v1/reshape"
    body: dict[str, Any] = {
        "stage1_output": stage1_output,
        "context": context_type,
        "purpose": purpose,
    }
    if view_ids:
        body["view_ids"] = view_ids
    if views:
        body["views"] = views
    started = time.perf_counter()
    response = await _request_with_retry(client, "POST", url, json=body)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "SystemDisplayPlugin reshape completed",
        extra={"event_type": "agent_reshape", "elapsed_ms": elapsed_ms, "status_code": response.status_code},
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SystemDisplayPlugin reshape failed: {response.status_code} {response.text}",
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SystemDisplayPlugin reshape returned a non-object body",
        )
    return payload


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            return await client.request(method, url, **kwargs)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt == 0:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Downstream request failed: {exc.__class__.__name__}",
            ) from exc
    assert last_exc is not None
    raise last_exc
