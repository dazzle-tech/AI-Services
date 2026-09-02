"""API authentication (disabled).

X-API-Key checks are off until re-enabled. Keep this module so staff/clinician
headers can be restored without rewriting routes.
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
