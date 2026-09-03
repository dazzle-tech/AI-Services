"""Optional request context. No headers are required."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AuthContext:
    api_key_valid: bool = True
    staff_id: Optional[str] = None
