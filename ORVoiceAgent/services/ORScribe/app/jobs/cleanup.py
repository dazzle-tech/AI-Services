"""Scheduled audio retention cleanup."""

from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.models import AudioChunkRecord, CaseRecord, CaseStatus
from app.jobs.celery_app import celery_app
from app.services.audit_service import AuditService
from app.storage.s3 import ObjectStorage

configure_logging()
logger = get_logger(__name__)


@celery_app.task(name="app.jobs.cleanup.cleanup_expired_audio")
def cleanup_expired_audio() -> int:
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
        CaseStatus.TRANSCRIBED,
        CaseStatus.NEEDS_REVIEW,
        CaseStatus.EXTRACTING_TIMELINE,
        CaseStatus.VERIFYING_CHECKLIST,
        CaseStatus.FINALIZING,
        CaseStatus.COMPLETED,
    }

    try:
        cases = (
            db.query(CaseRecord)
            .filter(
                CaseRecord.audio_uris.isnot(None),
                CaseRecord.audio_deleted_at.is_(None),
                CaseRecord.created_at <= cutoff,
                CaseRecord.status.in_(eligible_statuses),
            )
            .all()
        )

        for case in cases:
            for uri in case.audio_uris or []:
                storage.delete_audio(uri)
                deleted_count += 1
            case.audio_uris = []
            case.audio_deleted_at = datetime.now(timezone.utc)
            audit.log(
                case.id,
                "audio_deleted",
                details={"retention_days": settings.audio_retention_days},
            )

        db.commit()
        logger.info("Audio cleanup completed", extra={"case_id": "-", "event_type": "cleanup"})
        return deleted_count
    finally:
        db.close()
