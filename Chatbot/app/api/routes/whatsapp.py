"""WhatsApp webhook adapter routes for MedAI Assistant."""
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, List

import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.core.config import settings
from app.infrastructure.db.audit_repo import AuditRepository
from app.services.identity import get_identity_resolver
from app.services.session_memory import SessionMemoryService
from app.services.whatsapp_provider import get_whatsapp_provider
from app.infrastructure.http.clients import post_json_logged

logger = logging.getLogger(__name__)
router = APIRouter()

_identity_resolver = get_identity_resolver()
_session_memory = SessionMemoryService()
_audit_repo = AuditRepository()
_provider = get_whatsapp_provider()


def _format_whatsapp_safe(text: str) -> str:
    """Convert HTML/markdown-ish text into WhatsApp-safe plain text."""
    if not text:
        return ""
    # Strip raw HTML tags
    safe = text
    safe = _strip_html_tags(safe)
    safe = safe.replace("**", "*")
    safe = safe.replace("__", "_")
    safe = safe.replace("<br>", "\n")
    safe = safe.replace("<br/>", "\n")
    safe = safe.replace("<p>", "\n")
    safe = safe.replace("</p>", "\n")
    safe = safe.replace("<strong>", "*")
    safe = safe.replace("</strong>", "*")
    safe = safe.replace("<em>", "_")
    safe = safe.replace("</em>", "_")
    safe = safe.replace("&nbsp;", " ")
    safe = safe.replace("&amp;", "&")
    safe = safe.replace("&lt;", "<")
    safe = safe.replace("&gt;", ">")
    safe = safe.strip()
    safe = _convert_small_tables_to_text(safe)
    return safe


def _strip_html_tags(text: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", text)


def _convert_small_tables_to_text(text: str) -> str:
    lines = text.splitlines()
    if any("|" in line for line in lines):
        # Convert pipe tables to simple aligned text lists
        converted: List[str] = []
        for line in lines:
            row = [cell.strip() for cell in line.split("|") if cell.strip()]
            if len(row) > 1:
                converted.append(" - ".join(row))
            else:
                converted.append(line)
        return "\n".join(converted)
    return text


def _chunk_whatsapp_message(text: str) -> List[str]:
    limit = settings.whatsapp_max_message_length or 4096
    chunks: List[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    return chunks


def _log_whatsapp_event(direction: str, phone_number: str, user_id: str | None, message_text: str, status: str, error: str = ""):
    try:
        _audit_repo.insert_whatsapp_message(
            direction=direction,
            phone_number=phone_number,
            user_id=user_id,
            message_text=message_text,
            status=status,
            error=error,
        )
    except Exception as exc:
        logger.warning("Failed to audit WhatsApp message: %s", exc)


@router.get("/webhook/whatsapp")
def whatsapp_verify(request: Request) -> Response:
    """WhatsApp webhook verification handshake."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode != "subscribe" or token != settings.whatsapp_verify_token or not challenge:
        raise HTTPException(status_code=403, detail="Webhook verification failed.")

    logger.info("WhatsApp webhook verified successfully")
    return Response(content=challenge, media_type="text/plain")


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request) -> JSONResponse:
    """Receive inbound WhatsApp messages."""
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    if not _provider.verify_signature(raw_body, headers):
        logger.warning("Rejected WhatsApp webhook due to invalid signature")
        raise HTTPException(status_code=403, detail="Invalid webhook signature.")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse WhatsApp webhook payload: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid payload.")

    entries = payload.get("entry", [])
    # Fast health check before doing full work
    try:
        health_resp = requests.get(f"{settings.orchestrator_url}/health", timeout=2)
        if health_resp.status_code != 200:
            raise RuntimeError(f"orchestrator unhealthy: {health_resp.status_code}")
    except Exception as exc:
        logger.warning("WhatsApp adapter cannot reach orchestrator health: %s", exc)
        raise HTTPException(status_code=503, detail="Hospital chat pipeline unavailable.")

    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])
            for message in messages:
                phone_number = message.get("from")
                text = message.get("text", {}).get("body", "").strip()
                if not phone_number or not text:
                    continue

                _log_whatsapp_event(
                    direction="inbound",
                    phone_number=phone_number,
                    user_id=None,
                    message_text=text,
                    status="received",
                )

                resolved = _identity_resolver.resolve_from_phone(phone_number)
                if not resolved:
                    reply = (
                        "You're not a registered user of this hospital's assistant — "
                        f"contact {settings.hospital_admin_contact} to register."
                    )
                    _provider.send_typing_indicator(phone_number)
                    for chunk in _chunk_whatsapp_message(_format_whatsapp_safe(reply)):
                        _provider.send_text_message(phone_number, chunk)
                    _log_whatsapp_event(
                        direction="outbound",
                        phone_number=phone_number,
                        user_id=None,
                        message_text=reply,
                        status="unregistered",
                    )
                    continue

                phone_session = _session_memory.get_session(phone_number)
                session_id = phone_session.get("session_id")
                if not session_id:
                    session_id = f"whatsapp_{int(time.time())}_{phone_number[-6:]}"
                phone_session["session_id"] = session_id
                _session_memory.save_session(phone_number, phone_session)

                _provider.send_typing_indicator(phone_number)

                # Forward to orchestrator chat endpoint with server-resolved identity
                orchestrator_url = f"{settings.orchestrator_url}/chat"
                payload = {
                    "message": text,
                    "session_id": session_id,
                    "user_id": resolved.user_id,
                    "role": resolved.role,
                }

                try:
                    ok, response_body, err, status_code, latency_ms = post_json_logged(
                        interaction_id=None,
                        service="orchestrator",
                        url=orchestrator_url,
                        payload=payload,
                        audit_service=None,
                        timeout=settings.whatsapp_pipeline_timeout_secs,
                    )
                except Exception as exc:
                    logger.warning("Orchestrator request exception for WhatsApp: %s", exc)
                    ok = False
                    response_body = None
                    err = str(exc)

                if not ok or not response_body:
                    reply = "I'm having trouble reaching hospital systems right now, please try again shortly."
                    _provider.send_text_message(phone_number, _format_whatsapp_safe(reply))
                    _log_whatsapp_event(
                        direction="outbound",
                        phone_number=phone_number,
                        user_id=resolved.user_id,
                        message_text=reply,
                        status="error",
                        error=err or "orchestrator_error",
                    )
                    continue

                text_reply = response_body.get("text", "")
                safe_reply = _format_whatsapp_safe(text_reply)
                for chunk in _chunk_whatsapp_message(safe_reply):
                    _provider.send_text_message(phone_number, chunk)
                _log_whatsapp_event(
                    direction="outbound",
                    phone_number=phone_number,
                    user_id=resolved.user_id,
                    message_text=safe_reply,
                    status="delivered",
                )

    return JSONResponse(status_code=200, content={"ok": True})
