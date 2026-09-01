"""API authentication and role-based access control."""

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from app.core.config import settings
from app.db.models import SessionRecord


@dataclass
class AuthContext:
    """Authenticated request context."""

    api_key_valid: bool
    clinician_id: Optional[str] = None
    role: str = "clinician"


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> AuthContext:
    """Validate API key on every request."""
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return AuthContext(api_key_valid=True)


def get_clinician_context(
    auth: AuthContext = Depends(verify_api_key),
    x_clinician_id: Optional[str] = Header(None, alias="X-Clinician-Id"),
) -> AuthContext:
    """Attach clinician identity for RBAC-protected endpoints."""
    if not x_clinician_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Clinician-Id header required",
        )
    auth.clinician_id = x_clinician_id
    return auth


def assert_session_access(session: SessionRecord, clinician_id: str) -> None:
    """Ensure the clinician may access this session."""
    if session.clinician_id and session.clinician_id != clinician_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: session belongs to another clinician",
        )
