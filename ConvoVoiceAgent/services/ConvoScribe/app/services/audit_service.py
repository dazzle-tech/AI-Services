"""Audit log helpers."""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import AuditLog


class AuditService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def log(
        self,
        session_id: UUID,
        event_type: str,
        *,
        actor: str = "system",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        safe_details = _scrub_details(details or {})
        entry = AuditLog(
            session_id=session_id,
            event_type=event_type,
            actor=actor,
            details=safe_details,
        )
        self._db.add(entry)
        self._db.commit()


def _scrub_details(details: dict[str, Any]) -> dict[str, Any]:
    """Remove transcript/summary body content from audit payloads."""
    blocked_keys = {"text", "raw_transcript", "summary", "transcript", "segments"}
    cleaned: dict[str, Any] = {}
    for key, value in details.items():
        if key in blocked_keys:
            cleaned[key] = "[REDACTED]"
        elif isinstance(value, dict):
            cleaned[key] = _scrub_details(value)
        else:
            cleaned[key] = value
    return cleaned
