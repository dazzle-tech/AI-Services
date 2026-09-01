"""Scheduled audio retention cleanup."""

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.models import SessionRecord, SessionStatus
from app.db.session import get_engine
from app.jobs.celery_app import celery_app
from app.services.audit_service import AuditService
from app.storage.s3 import ObjectStorage

configure_logging()
logger = get_logger(__name__)


@celery_app.task(name="app.jobs.cleanup.cleanup_expired_audio")
def cleanup_expired_audio() -> int:
    """Delete raw audio after retention period once transcription is complete."""
    from app.db import session as db_session

    if db_session.SessionLocal is None:
        db_session.get_engine()
    assert db_session.SessionLocal is not None
    db = db_session.SessionLocal()
    storage = ObjectStorage()
    audit = AuditService(db)
    deleted_count = 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.audio_retention_days)
    eligible_statuses = {
        SessionStatus.TRANSCRIBED,
        SessionStatus.NEEDS_REVIEW,
        SessionStatus.SUMMARIZING,
        SessionStatus.COMPLETED,
    }

    try:
        sessions = (
            db.query(SessionRecord)
            .filter(
                SessionRecord.audio_uri.isnot(None),
                SessionRecord.audio_deleted_at.is_(None),
                SessionRecord.created_at <= cutoff,
                SessionRecord.status.in_(eligible_statuses),
            )
            .all()
        )

        for session in sessions:
            if session.audio_uri:
                storage.delete_audio(session.audio_uri)
                session.audio_uri = None
                session.audio_deleted_at = datetime.now(timezone.utc)
                deleted_count += 1
                audit.log(
                    session.id,
                    "audio_deleted",
                    details={"retention_days": settings.audio_retention_days},
                )

        db.commit()
        logger.info(
            "Audio cleanup completed",
            extra={"session_id": "-", "event_type": "cleanup", },
        )
        return deleted_count
    finally:
        db.close()
