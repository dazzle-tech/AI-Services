"""Meta WhatsApp Business Cloud API client for the patient agent.

Matches ``Chatbot/app/services/whatsapp_provider.py``: webhook signature check,
mark-as-read + typing bubble, and text replies.
"""
import hashlib
import hmac
import logging
from typing import Any, Dict

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class MetaWhatsAppProvider:
    def __init__(self) -> None:
        self.verify_token = settings.whatsapp_verify_token
        self.access_token = settings.whatsapp_access_token
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.api_version = settings.whatsapp_api_version
        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"

    def verify_signature(self, raw_body: bytes, headers: Dict[str, str]) -> bool:
        signature = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256")
        if not signature or not signature.startswith("sha256="):
            logger.warning("WhatsApp signature missing or malformed: %s", signature)
            return False
        expected = hmac.new(self._app_secret_bytes(), raw_body, hashlib.sha256).hexdigest()
        actual = signature.split("=", 1)[1]
        valid = hmac.compare_digest(expected, actual)
        if not valid:
            logger.warning("WhatsApp signature validation failed")
        return valid

    def send_typing_indicator(self, message_id: str) -> bool:
        """Mark the inbound message as read and show the typing bubble.

        Meta Cloud API (v25+) removed standalone ``type: typing_on``. Seen + typing
        are now a status update tied to the inbound ``wamid``:

            POST /{phone_number_id}/messages
            {
              "messaging_product": "whatsapp",
              "status": "read",
              "message_id": "<wamid>",
              "typing_indicator": {"type": "text"}
            }

        Auto-clears after ~25s or when we send the reply. Call once per inbound
        message, before the (slow) agent turn.
        """
        if not message_id:
            logger.warning("Cannot show typing indicator without a message_id")
            return False
        if not self._ready():
            logger.warning("WhatsApp provider is not configured; cannot show typing indicator")
            return False
        return self._post({
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
            "typing_indicator": {"type": "text"},
        })

    def send_text_message(self, phone_number: str, text: str) -> bool:
        if not self._ready():
            logger.warning("WhatsApp provider is not configured; cannot send text")
            return False
        body = (text or "")[: settings.whatsapp_max_message_length]
        if not body:
            return False
        return self._post({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone_number,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        })

    def _post(self, payload: Dict[str, Any]) -> bool:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                f"{self.base_url}/messages", json=payload, headers=headers, timeout=10,
            )
            if response.status_code >= 400:
                logger.warning("WhatsApp send failed %s: %s", response.status_code, response.text)
                return False
            return True
        except Exception as exc:
            logger.warning("WhatsApp send exception: %s", exc)
            return False

    def _app_secret_bytes(self) -> bytes:
        return (settings.whatsapp_app_secret or "").encode("utf-8")

    def _ready(self) -> bool:
        return bool(self.access_token and self.phone_number_id and settings.whatsapp_app_secret)


_provider: MetaWhatsAppProvider | None = None


def get_whatsapp_provider() -> MetaWhatsAppProvider:
    global _provider
    if _provider is None:
        _provider = MetaWhatsAppProvider()
    return _provider
