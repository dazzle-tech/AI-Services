"""WhatsApp webhook for the patient agent.

Same Meta handshake, seen/typing, dedup, and reply path as
``Chatbot/app/api/routes/whatsapp.py``, but the turn runs in-process
(phone → patient_id → ``/agent/chat``) instead of hopping to an orchestrator.
Webhook URL: ``GET/POST /webhook/whatsapp`` on port 8030.
"""
import json
import logging
import re
import time
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.api.routes.agent import chat
from app.core.config import settings
from app.infrastructure.phone_identity import resolve_patient_from_phone
from app.infrastructure.session_store import get_session_store
from app.infrastructure.whatsapp_provider import get_whatsapp_provider
from app.models import schemas

logger = logging.getLogger(__name__)
router = APIRouter()
_provider = get_whatsapp_provider()
_dedup_store = get_session_store()
_local_dedup: Dict[str, float] = {}


def _already_processed(message_id: str) -> bool:
    """True if this inbound WhatsApp message id was already handled.

    Meta retries webhooks that are slow; without this the patient gets duplicate replies.
    """
    if not message_id:
        return False
    try:
        client = getattr(_dedup_store, "_client", None)
        if client is not None:
            was_set = client.set(f"medai:patient-wa-dedup:{message_id}", "1", nx=True, ex=86400)
            return not was_set
    except Exception as exc:
        logger.warning("Dedup check failed, using in-process fallback: %s", exc)

    now = time.time()
    stale = [key for key, ts in _local_dedup.items() if now - ts > 86400]
    for key in stale:
        _local_dedup.pop(key, None)
    if message_id in _local_dedup:
        return True
    _local_dedup[message_id] = now
    return False


def _format_whatsapp_safe(text: str) -> str:
    if not text:
        return ""
    safe = re.sub(r"<[^>]+>", "", text)
    safe = safe.replace("**", "*").replace("__", "_")
    safe = safe.replace("&nbsp;", " ").replace("&amp;", "&")
    safe = safe.replace("&lt;", "<").replace("&gt;", ">")
    lines = []
    for line in safe.splitlines():
        if "|" in line:
            row = [cell.strip() for cell in line.split("|") if cell.strip()]
            lines.append(" - ".join(row) if len(row) > 1 else line)
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def _humanize_field_name(key: str) -> str:
    name = str(key or "")
    for prefix in ("patients_", "patient_details_", "patient_health_", "address_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    name = name.replace("_", " ").strip()
    return name[:1].upper() + name[1:] if name else name


def _format_fields_block(fields: Dict[str, Any], columns: List[str] = None) -> str:
    keys = columns or list(fields.keys())
    lines: List[str] = []
    for key in keys:
        if key not in fields:
            continue
        value = fields[key]
        if value is None or value == "" or value == "N/A":
            continue
        if isinstance(value, bool):
            value = "Yes" if value else "No"
        if isinstance(value, (dict, list)):
            continue
        lines.append(f"{_humanize_field_name(key)}: {value}")
    return "\n".join(lines)


def _format_data_json_for_whatsapp(data_json: Dict[str, Any] | None) -> str:
    """Expand structured tool output so WhatsApp gets the same facts as the web cards."""
    if not data_json:
        return ""

    columns = data_json.get("columns") if isinstance(data_json, dict) else None
    record = data_json.get("record") if isinstance(data_json, dict) else None
    if isinstance(record, dict) and record:
        return _format_fields_block(record, columns)

    rows = data_json.get("table") if isinstance(data_json, dict) else None
    if isinstance(rows, list) and rows:
        return _format_row_list(rows, columns, data_json.get("count"))

    # Patient tools: appointments / slots / upcoming lists
    for key in ("upcoming", "slots", "appointments", "results"):
        items = data_json.get(key) if isinstance(data_json, dict) else None
        if isinstance(items, list) and items and isinstance(items[0], dict):
            return _format_row_list(items, None, len(items))

    if isinstance(data_json, dict) and any(
        not isinstance(v, (dict, list)) for v in data_json.values()
    ):
        return _format_fields_block(data_json)
    return ""


def _format_row_list(rows: List[Any], columns: List[str] | None, total: Any) -> str:
    max_rows = 15
    shown = rows[:max_rows]
    if len(shown) == 1 and isinstance(shown[0], dict):
        return _format_fields_block(shown[0], columns)
    blocks: List[str] = []
    for i, row in enumerate(shown, start=1):
        if not isinstance(row, dict):
            continue
        blocks.append(f"{i}) " + _format_fields_block(row, columns).replace("\n", "\n   "))
    combined = "\n\n".join(blocks)
    count = int(total) if total else len(rows)
    if count > len(shown):
        combined += f"\n\n...and {count - len(shown)} more result(s)."
    return combined


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


def _send(phone_number: str, text: str) -> None:
    for chunk in _chunk_whatsapp_message(_format_whatsapp_safe(text)):
        _provider.send_text_message(phone_number, chunk)


def _preview(text: str, limit: int = 120) -> str:
    one_line = " ".join((text or "").split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 3] + "..."


def _summarize_webhook_payload(payload: Dict[str, Any]) -> str:
    """Short summary for logs — Meta sends many status-only POSTs with no messages."""
    parts: List[str] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            msgs = value.get("messages") or []
            statuses = value.get("statuses") or []
            if msgs:
                parts.append(f"messages={len(msgs)}")
            if statuses:
                parts.append(f"statuses={len(statuses)}")
            if not msgs and not statuses:
                parts.append("empty-change")
    return ", ".join(parts) if parts else "no-entry"


def _normalize_from(raw_phone_number: str) -> str:
    # Meta "from" is country code + number with no leading "+".
    if raw_phone_number.startswith("+"):
        return raw_phone_number
    return f"+{raw_phone_number}"


@router.get("/webhook/whatsapp")
def whatsapp_verify(request: Request) -> Response:
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode != "subscribe" or token != settings.whatsapp_verify_token or not challenge:
        raise HTTPException(status_code=403, detail="Webhook verification failed.")
    logger.info("WhatsApp webhook verified successfully")
    return Response(content=challenge, media_type="text/plain")


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request) -> JSONResponse:
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    if not _provider.verify_signature(raw_body, headers):
        logger.warning("Rejected WhatsApp webhook due to invalid signature")
        raise HTTPException(status_code=403, detail="Invalid webhook signature.")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse WhatsApp webhook payload: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid payload.") from exc

    summary = _summarize_webhook_payload(payload)
    logger.info("WhatsApp webhook POST received (%s)", summary)

    handled = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for message in change.get("value", {}).get("messages", []):
                message_id = message.get("id") or ""
                msg_type = message.get("type") or "unknown"
                if _already_processed(message_id):
                    logger.info(
                        "WhatsApp dedup skip id=%s type=%s (Meta retry)",
                        message_id, msg_type,
                    )
                    continue
                raw_phone = message.get("from")
                text = (message.get("text") or {}).get("body", "").strip()
                if not raw_phone or not text:
                    logger.info(
                        "WhatsApp skip non-text inbound id=%s type=%s from=%s",
                        message_id, msg_type, raw_phone or "(missing)",
                    )
                    continue
                handled += 1
                _handle_inbound(_normalize_from(raw_phone), text, message_id)

    if handled:
        logger.info("WhatsApp webhook handled %s inbound message(s)", handled)
    return JSONResponse(status_code=200, content={"ok": True})


def _handle_inbound(phone_number: str, text: str, message_id: str) -> None:
    logger.info(
        "WhatsApp IN from=%s id=%s text=%r",
        phone_number, message_id, _preview(text, 200),
    )
    resolved = resolve_patient_from_phone(phone_number)
    if resolved:
        logger.info(
            "WhatsApp patient resolved id=%s mrn=%s name=%r",
            resolved.patient_id,
            resolved.medical_record_number,
            resolved.patient_name,
        )
    else:
        logger.warning("WhatsApp patient NOT found for phone=%s", phone_number)

    _provider.send_typing_indicator(message_id)

    if not resolved:
        reply = (
            "You're not a registered patient of this hospital's assistant — "
            f"contact {settings.hospital_admin_contact} to register."
        )
        logger.info("WhatsApp OUT to=%s (unregistered): %r", phone_number, _preview(reply))
        _send(phone_number, reply)
        return

    session_id = f"whatsapp_{''.join(ch for ch in phone_number if ch.isdigit())}"
    try:
        response = chat(schemas.PatientChatRequest(
            message=text,
            session_id=session_id,
            patient_id=resolved.patient_id,
            patient_mrn=resolved.medical_record_number,
            patient_name=resolved.patient_name,
            user_id=f"patient_{resolved.patient_id}",
            role="patient",
        ))
        details = _format_data_json_for_whatsapp(response.data_json)
        reply = response.text or ""
        if details:
            reply = f"{reply}\n\n{details}" if reply else details
        if not reply:
            reply = "Sorry — I could not complete that just now. Please try again."
        logger.info(
            "WhatsApp agent reply session=%s intent=%s text=%r",
            session_id,
            getattr(response, "intent", None),
            _preview(reply, 300),
        )
    except HTTPException as exc:
        logger.warning("WhatsApp chat refused for %s: %s", phone_number, exc.detail)
        reply = str(exc.detail)
    except Exception:
        logger.exception("WhatsApp chat failed for %s", phone_number)
        reply = "I'm having trouble reaching hospital systems right now, please try again shortly."

    logger.info("WhatsApp OUT to=%s id=%s: %r", phone_number, message_id, _preview(reply, 300))
    _send(phone_number, reply)
