"""Append-only audit log helpers."""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import AuditLog


class AuditService:
    """Append-only audit trail — no updates or deletes at application level."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def log(
        self,
        case_id: UUID,
        event_type: str,
        *,
        actor: str = "system",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        safe_details = _scrub_details(details or {})
        entry = AuditLog(
            case_id=case_id,
            event_type=event_type,
            actor=actor,
            details=safe_details,
        )
        self._db.add(entry)
        self._db.commit()


def _scrub_details(details: dict[str, Any]) -> dict[str, Any]:
    blocked_keys = {"text", "raw_transcript", "transcript", "segments", "description"}
    cleaned: dict[str, Any] = {}
    for key, value in details.items():
        if key in blocked_keys:
            cleaned[key] = "[REDACTED]"
        elif isinstance(value, dict):
            cleaned[key] = _scrub_details(value)
        else:
            cleaned[key] = value
    return cleaned
