"""API authentication and role-based access control."""

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from app.core.config import settings
from app.db.models import CaseRecord


@dataclass
class AuthContext:
    """Authenticated request context."""

    api_key_valid: bool
    staff_id: Optional[str] = None
    role: str = "or_staff"


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> AuthContext:
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return AuthContext(api_key_valid=True)


def get_staff_context(
    auth: AuthContext = Depends(verify_api_key),
    x_staff_id: Optional[str] = Header(None, alias="X-Staff-Id"),
) -> AuthContext:
    if not x_staff_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Staff-Id header required",
        )
    auth.staff_id = x_staff_id
    return auth


def assert_case_access(case: CaseRecord, staff_id: str) -> None:
    if case.created_by and case.created_by != staff_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: case belongs to another staff member",
        )
