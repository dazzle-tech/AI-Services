"""API authentication (disabled).

Request headers are not required. Keep this module so staff/clinician
checks can be restored without rewriting routes.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AuthContext:
    """Authenticated request context."""

    api_key_valid: bool = True
    clinician_id: Optional[str] = None
    role: str = "clinician"


def verify_api_key() -> AuthContext:
    """Return an anonymous context (no headers required)."""
    return AuthContext()
