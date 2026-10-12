"""API authentication (disabled).

Request headers are not required. Keep this module so staff/clinician
checks can be restored without rewriting routes.
"""

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, status

from app.db.models import SessionRecord


@dataclass
class AuthContext:
    """Authenticated request context."""

    api_key_valid: bool = True
    clinician_id: Optional[str] = None
    role: str = "clinician"


def get_clinician_context() -> AuthContext:
    """Return an anonymous clinician context (no headers required)."""
    return AuthContext()


def assert_session_access(session: SessionRecord, clinician_id: str) -> None:
    """Ensure the clinician may access this session."""
    if session.clinician_id and session.clinician_id != clinician_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: session belongs to another clinician",
        )
