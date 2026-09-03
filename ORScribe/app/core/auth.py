"""Optional request context. No headers are required."""

from dataclasses import dataclass
from typing import Optional

from app.db.models import CaseRecord


@dataclass
class AuthContext:
    api_key_valid: bool = True
    staff_id: Optional[str] = None
    role: str = "or_staff"


def get_staff_context() -> AuthContext:
    return AuthContext()


def assert_case_access(case: CaseRecord, staff_id: Optional[str]) -> None:
    return
