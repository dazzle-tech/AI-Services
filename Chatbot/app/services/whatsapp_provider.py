"""WhatsApp provider abstraction for MedAI Assistant."""
import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

import requests
from app.core.config import settings

logger = logging.getLogger(__name__)


class WhatsAppProvider:
    """Abstraction layer for WhatsApp provider integrations."""

    def verify_signature(self, raw_body: bytes, headers: Dict[str, str]) -> bool:
        raise NotImplementedError

    def send_typing_indicator(self, phone_number: str) -> bool:
        raise NotImplementedError

    def send_text_message(self, phone_number: str, text: str) -> bool:
        raise NotImplementedError


class MetaWhatsAppProvider(WhatsAppProvider):
    """Meta WhatsApp Business Cloud API provider."""

    def __init__(self):
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

        expected = hmac.new(
            self._app_secret_bytes(), raw_body, hashlib.sha256
        ).hexdigest()
        actual = signature.split("=", 1)[1]
        valid = hmac.compare_digest(expected, actual)
        if not valid:
            logger.warning("WhatsApp signature validation failed")
        return valid

    def send_typing_indicator(self, phone_number: str) -> bool:
        if not self._ready():
            logger.debug("WhatsApp provider not ready for typing indicator")
            return False

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone_number,
            "type": "typing_on",
        }
        return self._post(payload)

    def send_text_message(self, phone_number: str, text: str) -> bool:
        if not self._ready():
            logger.warning("WhatsApp provider is not configured; cannot send text message")
            return False

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone_number,
            "type": "text",
            "text": {"preview_url": False, "body": text[: settings.whatsapp_max_message_length]},
        }
        return self._post(payload)

    def _post(self, payload: Dict[str, Any]) -> bool:
        url = f"{self.base_url}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code >= 400:
                logger.warning(
                    "WhatsApp send failed %s: %s",
                    response.status_code,
                    response.text,
                )
                return False
            return True
        except Exception as exc:
            logger.warning("WhatsApp send exception: %s", exc)
            return False

    def _app_secret_bytes(self) -> bytes:
        secret = settings.whatsapp_app_secret or ""
        return secret.encode("utf-8")

    def _ready(self) -> bool:
        return bool(self.access_token and self.phone_number_id and settings.whatsapp_app_secret)


def get_whatsapp_provider() -> WhatsAppProvider:
    return MetaWhatsAppProvider()
