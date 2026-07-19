"""One-time confirmation token service for protected write actions."""
import json
import logging
import secrets
import time
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False
    logger.warning(
        "Redis is not installed; confirmation tokens will use in-memory fallback storage."
    )


class ConfirmationService:
    """Generate and validate short-lived confirmation tokens."""

    def __init__(self):
        self.ttl = settings.confirmation_token_ttl_seconds
        self._client = None
        self._fallback: dict[str, tuple[str, float]] = {}

        if REDIS_AVAILABLE and redis is not None:
            try:
                self._client = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    db=settings.redis_db,
                    decode_responses=True,
                    socket_connect_timeout=3,
                )
                self._client.ping()
            except Exception as exc:
                logger.warning("Confirmation token Redis unavailable: %s", exc)
                self._client = None

    def _key(self, token: str) -> str:
        return f"medai:confirmation:{token}"

    def generate(
        self,
        user_id: str,
        role: str,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        token = secrets.token_urlsafe(16)
        data = {
            "user_id": user_id,
            "role": role,
            "action": action,
            "payload": payload or {},
            "created_at": time.time(),
            "expires_at": time.time() + self.ttl,
            "used": False,
        }
        key = self._key(token)

        if self._client:
            self._client.setex(key, self.ttl, json.dumps(data))
        else:
            self._fallback[key] = (json.dumps(data), time.time() + self.ttl)

        logger.info(
            "Confirmation token generated for user=%s action=%s token=%s",
            user_id,
            action,
            token,
        )
        return token

    def validate(self, token: str, user_id: Optional[str] = None, action: Optional[str] = None) -> Optional[Dict[str, Any]]:
        key = self._key(token)
        data_json = None

        if self._client:
            stored = self._client.get(key)
            if stored:
                try:
                    data_json = json.loads(stored)
                except Exception:
                    data_json = None
        else:
            entry = self._fallback.get(key)
            if entry:
                stored, expires = entry
                if time.time() > expires:
                    self._fallback.pop(key, None)
                    return None
                try:
                    data_json = json.loads(stored)
                except Exception:
                    data_json = None

        if not data_json:
            return None
        if data_json.get("used"):
            return None
        if user_id and data_json.get("user_id") != user_id:
            return None
        if action and data_json.get("action") != action:
            return None
        if time.time() > float(data_json.get("expires_at", 0)):
            self.consume(token)
            return None

        self.consume(token)
        return data_json

    def consume(self, token: str) -> None:
        key = self._key(token)
        if self._client:
            try:
                self._client.delete(key)
            except Exception:
                pass
        else:
            self._fallback.pop(key, None)


_confirmation_service = ConfirmationService()


def get_confirmation_service() -> ConfirmationService:
    return _confirmation_service
