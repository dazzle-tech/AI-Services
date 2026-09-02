"""API authentication (X-API-Key disabled).

X-API-Key checks are off until re-enabled. Keep this module so clinician
headers can be restored without rewriting routes.
"""

from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, status

from app.db.models import SessionRecord


@dataclass
class AuthContext:
    """Authenticated request context."""

    api_key_valid: bool
    clinician_id: Optional[str] = None
    role: str = "clinician"


def get_clinician_context(
    x_clinician_id: Optional[str] = Header(None, alias="X-Clinician-Id"),
) -> AuthContext:
    """Attach clinician identity for RBAC-protected endpoints."""
    if not x_clinician_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Clinician-Id header required",
        )
    return AuthContext(api_key_valid=True, clinician_id=x_clinician_id)


def assert_session_access(session: SessionRecord, clinician_id: str) -> None:
    """Ensure the clinician may access this session."""
    if session.clinician_id and session.clinician_id != clinician_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: session belongs to another clinician",
        )
