"""Server-side identity resolution — sole source of truth for user_id and role."""
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request

from app.core.config import settings
from app.infrastructure.config.access_control_repo import AccessControlRepository

logger = logging.getLogger(__name__)

_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


@dataclass(frozen=True)
class ResolvedIdentity:
    """Authenticated identity for a request."""

    user_id: str
    role: str
    channel: str  # web | whatsapp | internal


class IdentityResolver:
    """
    Resolves user_id and role from server-side credentials only.

    Client-supplied user_id/role are never trusted directly — they may be used
    as hints for validation against the resolved identity.
    """

    def __init__(
        self,
        access_control: Optional[AccessControlRepository] = None,
        registered_users_repo=None,
    ):
        self._access_control = access_control or AccessControlRepository()
        self._registered_users_repo = registered_users_repo
        self._web_tokens = self._load_web_tokens()

    def _load_web_tokens(self) -> dict[str, str]:
        raw = (settings.web_auth_tokens or "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            logger.warning("Invalid WEB_AUTH_TOKENS JSON; web auth tokens disabled")
        return {}

    def _role_for_user(self, user_id: str) -> str:
        return self._access_control.get_user_role(user_id)

    def _validate_user_exists(self, user_id: str) -> None:
        access = self._access_control.get_user_access(user_id)
        if not access:
            raise HTTPException(status_code=403, detail="Unknown or unauthorized user.")

    def resolve_from_web(
        self,
        request: Request,
        user_id_hint: Optional[str] = None,
    ) -> ResolvedIdentity:
        """
        Resolve identity for the web UI channel.

        Requires Authorization: Bearer <token> mapped in WEB_AUTH_TOKENS unless
        WEB_AUTH_DEV_MODE is enabled (development only).
        """
        token_user_id: Optional[str] = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            token_user_id = self._web_tokens.get(token)

        if token_user_id:
            if user_id_hint and user_id_hint != token_user_id:
                logger.warning(
                    "user_id hint %s does not match token identity %s",
                    user_id_hint,
                    token_user_id,
                )
                raise HTTPException(
                    status_code=403,
                    detail="user_id does not match authenticated identity.",
                )
            self._validate_user_exists(token_user_id)
            role = self._role_for_user(token_user_id)
            return ResolvedIdentity(user_id=token_user_id, role=role, channel="web")

        if settings.web_auth_dev_mode:
            candidate = (user_id_hint or "default_user").strip()
            self._validate_user_exists(candidate)
            role = self._role_for_user(candidate)
            logger.warning(
                "WEB_AUTH_DEV_MODE: accepting user_id=%s without bearer token (dev only)",
                candidate,
            )
            return ResolvedIdentity(user_id=candidate, role=role, channel="web")

        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide Authorization: Bearer <token>.",
        )

        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide Authorization: Bearer <token>.",
        )

    def resolve_internal_request(
        self,
        request: Request,
        user_id: str,
        role: str,
    ) -> ResolvedIdentity:
        """Resolve identity for internal service-to-service calls."""
        internal_token = request.headers.get("X-Internal-Service-Token", "").strip()
        if not internal_token or internal_token != settings.internal_service_token:
            logger.warning(
                "Rejected internal request due to missing or invalid internal service token"
            )
            raise HTTPException(status_code=401, detail="Internal service authentication failed.")

        self._validate_user_exists(user_id)
        resolved_role = self._role_for_user(user_id)
        if role != resolved_role:
            logger.warning(
                "Internal request role mismatch for user_id=%s: claimed=%s resolved=%s",
                user_id,
                role,
                resolved_role,
            )
            raise HTTPException(
                status_code=403,
                detail="Internal request role does not match resolved identity.",
            )
        return ResolvedIdentity(user_id=user_id, role=resolved_role, channel="internal")

    @staticmethod
    def normalize_phone(phone_number: str) -> str:
        """Normalize to E.164 (+digits only)."""
        cleaned = re.sub(r"[^\d+]", "", phone_number or "")
        if not cleaned.startswith("+"):
            default_cc = (settings.default_phone_country_code or "+1").strip()
            if not default_cc.startswith("+"):
                default_cc = f"+{default_cc}"
            cleaned = f"{default_cc}{cleaned.lstrip('0')}"
        if not _E164_RE.match(cleaned):
            raise ValueError(f"Invalid E.164 phone number: {phone_number!r}")
        return cleaned

    def resolve_from_phone(self, phone_number: str) -> Optional[ResolvedIdentity]:
        """
        Resolve identity from a WhatsApp phone number via registered_users store.

        Returns None if not found, inactive, or not OTP-verified.
        """
        if self._registered_users_repo is None:
            from app.infrastructure.db.registered_users_repo import RegisteredUsersRepository

            self._registered_users_repo = RegisteredUsersRepository()

        try:
            normalized = self.normalize_phone(phone_number)
        except ValueError:
            logger.warning("Invalid phone number for identity lookup: %s", phone_number)
            return None

        record = self._registered_users_repo.get_by_phone(normalized)
        if not record or not record.get("active"):
            return None
        if not record.get("otp_verified"):
            return None

        user_id = record["user_id"]
        role = record.get("role") or self._role_for_user(user_id)
        return ResolvedIdentity(user_id=user_id, role=role, channel="whatsapp")

    def resolve_internal(self, user_id: str) -> ResolvedIdentity:
        """Resolve identity for trusted internal service-to-service calls."""
        self._validate_user_exists(user_id)
        role = self._role_for_user(user_id)
        return ResolvedIdentity(user_id=user_id, role=role, channel="internal")


_identity_resolver: Optional[IdentityResolver] = None


def get_identity_resolver() -> IdentityResolver:
    global _identity_resolver
    if _identity_resolver is None:
        _identity_resolver = IdentityResolver()
    return _identity_resolver
