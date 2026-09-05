"""Deterministic pipeline: ORScribe STT then the matching ORDisplayPlugin window."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.logging import get_logger
from app.core.window_registry import WINDOW_BY_ID, WindowSpec

logger = get_logger(__name__)

_RETRY_BACKOFF_SECONDS = 0.25


async def fill_window(
    spec: WindowSpec,
    *,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    role: Optional[str],
) -> dict[str, Any]:
    canon_role = (role or spec.role).strip() or spec.role

    timeout = httpx.Timeout(settings.http_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        transcript = await _transcribe(
            client,
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
            window_id=spec.window_id,
            role=canon_role,
        )
        extracted = await _extract(
            client,
            display_path=spec.display_path,
            role=canon_role,
            text=transcript,
            window_id=spec.window_id,
        )

    if isinstance(extracted, dict) and "raw_text" not in extracted:
        extracted = {**extracted, "raw_text": transcript}
    return extracted


def spec_for(window_id: str) -> WindowSpec:
    return WINDOW_BY_ID[window_id]


async def _transcribe(
    client: httpx.AsyncClient,
    *,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    window_id: str,
    role: str,
) -> str:
    url = f"{settings.orscribe_base_url.rstrip('/')}/api/v1/windows/transcribe"
    data = {
        "window_id": window_id,
        "role": role,
    }
    files = {"audio": (filename, audio_bytes, content_type)}

    started = time.perf_counter()
    response = await _request_with_retry(client, "POST", url, data=data, files=files)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "ORScribe transcribe completed",
        extra={
            "window_id": window_id,
            "event_type": "agent_transcribe",
            "elapsed_ms": elapsed_ms,
            "status_code": response.status_code,
        },
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ORScribe transcription failed: {response.status_code} {response.text}",
        )
    payload = response.json()
    return payload.get("text") or ""


async def _extract(
    client: httpx.AsyncClient,
    *,
    display_path: str,
    role: str,
    text: str,
    window_id: str,
) -> dict[str, Any]:
    url = f"{settings.ordisplay_base_url.rstrip('/')}{display_path}"
    body = {
        "role": role,
        "text": text,
    }
    started = time.perf_counter()
    response = await _request_with_retry(client, "POST", url, json=body)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "ORDisplayPlugin extract completed",
        extra={
            "window_id": window_id,
            "event_type": "agent_extract",
            "elapsed_ms": elapsed_ms,
            "status_code": response.status_code,
        },
    )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Field extraction failed: {response.status_code} {response.text}",
        )
    return _unwrap_display_payload(response.json(), window_id=window_id)


def _unwrap_display_payload(payload: dict[str, Any], *, window_id: str) -> dict[str, Any]:
    """Return EMR JSON — unwrap legacy WindowExtractResponse when DisplayPlugin still wraps."""
    if window_id == "nursing_verification_of_marking_site":
        return payload
    fields = payload.get("fields")
    if isinstance(fields, dict) and "window_id" in payload and "raw_text" in payload:
        return fields
    return payload


async def ping_downstream() -> dict[str, str]:
    timeout = httpx.Timeout(5.0)
    result = {"orscribe": "error", "ordisplay_plugin": "error"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            orscribe = await client.get(f"{settings.orscribe_base_url.rstrip('/')}/api/v1/health")
            result["orscribe"] = "ok" if orscribe.status_code == 200 else f"http_{orscribe.status_code}"
        except httpx.HTTPError as exc:
            result["orscribe"] = f"unreachable: {exc.__class__.__name__}"
        try:
            display = await client.get(f"{settings.ordisplay_base_url.rstrip('/')}/api/v1/health")
            result["ordisplay_plugin"] = "ok" if display.status_code == 200 else f"http_{display.status_code}"
        except httpx.HTTPError as exc:
            result["ordisplay_plugin"] = f"unreachable: {exc.__class__.__name__}"
    return result


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
            raise
    assert last_exc is not None
    raise last_exc
