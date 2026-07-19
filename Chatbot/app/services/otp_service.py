"""OTP generation and verification for patient self-registration."""
import logging
import random
import string
import time
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class OTPService:
    """Stores and verifies one-time passwords in Redis."""

    def __init__(self):
        self.ttl = settings.otp_ttl_seconds
        self.length = settings.otp_length
        self._client = None
        self._connected = False
        self._fallback: dict[str, tuple[str, float]] = {}

        if REDIS_AVAILABLE:
            try:
                self._client = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    db=settings.redis_db,
                    decode_responses=True,
                    socket_connect_timeout=3,
                )
                self._client.ping()
                self._connected = True
            except Exception as exc:
                logger.warning("OTP Redis unavailable: %s", exc)

    def _key(self, phone_number: str, purpose: str) -> str:
        return f"medai:otp:{purpose}:{phone_number}"

    def generate(self, phone_number: str, purpose: str = "registration") -> str:
        code = "".join(random.choices(string.digits, k=self.length))
        key = self._key(phone_number, purpose)
        if self._connected and self._client:
            self._client.setex(key, self.ttl, code)
        else:
            self._fallback[key] = (code, time.time() + self.ttl)
        logger.info("OTP generated for %s (purpose=%s)", phone_number, purpose)
        return code

    def verify(self, phone_number: str, code: str, purpose: str = "registration") -> bool:
        key = self._key(phone_number, purpose)
        expected: Optional[str] = None

        if self._connected and self._client:
            expected = self._client.get(key)
            if expected and expected == code.strip():
                self._client.delete(key)
                return True
            return False

        entry = self._fallback.get(key)
        if not entry:
            return False
        stored, expires = entry
        if time.time() > expires:
            self._fallback.pop(key, None)
            return False
        if stored == code.strip():
            self._fallback.pop(key, None)
            return True
        return False
