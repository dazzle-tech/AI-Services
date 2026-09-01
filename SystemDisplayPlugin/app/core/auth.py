"""API authentication.

Assumption: ORScribe requires X-API-Key + X-Staff-Id (case ownership);
ConvoScribe requires X-API-Key + X-Clinician-Id (session ownership).
View decoders here are shared configuration, not staff-owned cases, so
endpoints only require X-API-Key. Do not add X-Staff-Id unless product
wants per-staff decoder isolation.
"""

from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from app.core.config import settings


@dataclass
class AuthContext:
    """Authenticated request context."""

    api_key_valid: bool


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> AuthContext:
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return AuthContext(api_key_valid=True)
