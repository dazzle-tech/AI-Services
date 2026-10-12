"""Pipeline: ConvoScribe analyze, then SystemDisplayPlugin reshape."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_RETRY_BACKOFF_SECONDS = 0.25
_SOAP_KEYS = ("subjective", "objective", "assessment", "plan")


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


def stage1_output_from_analyze(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten ConvoScribe's clinical object so DisplayPlugin source paths match."""
    summary = payload.get("summary")
    if isinstance(summary, dict) and any(summary.get(key) for key in _SOAP_KEYS):
        return summary

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
        result["convoscribe"] = await _ping(client, settings.convoscribe_base_url)
        result["system_display_plugin"] = await _ping(client, settings.system_display_base_url)
    return result


async def _ping(client: httpx.AsyncClient, base_url: str) -> str:
    try:
        response = await client.get(f"{base_url.rstrip('/')}/api/v1/health")
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
) -> dict[str, Any]:
    url = f"{settings.convoscribe_base_url.rstrip('/')}/api/v1/analyze"
    data = {
        "context_type": context_type,
        "purpose": purpose,
        "detail_level": detail_level,
    }
    files = {"audio": (filename, audio_bytes, content_type)}
    started = time.perf_counter()
    response = await _request_with_retry(client, "POST", url, data=data, files=files)
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
    view_ids: list[str],
) -> dict[str, Any]:
    url = f"{settings.system_display_base_url.rstrip('/')}/api/v1/reshape"
    body = {
        "stage1_output": stage1_output,
        "context": context_type,
        "purpose": purpose,
        "view_ids": view_ids,
    }
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
