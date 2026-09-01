"""Background pipeline tasks."""

from __future__ import annotations

from uuid import UUID

from app.core.logging import configure_logging, get_logger
from app.db.models import SessionRecord, SessionStatus
from app.db.session import get_engine
from app.jobs.celery_app import celery_app
from app.services.audit_service import AuditService
from app.services.pipeline_service import (
    generate_clinical_summary,
    identify_speaker_roles,
    transcribe_audio,
)
from app.storage.s3 import ObjectStorage

configure_logging()
logger = get_logger(__name__)


def _open_db():
    from app.db import session as db_session

    if db_session.SessionLocal is None:
        db_session.get_engine()
    assert db_session.SessionLocal is not None
    return db_session.SessionLocal()


@celery_app.task(name="app.jobs.tasks.process_session_pipeline", bind=True, max_retries=2)
def process_session_pipeline(self, session_id: str, start_at: str = "transcribe") -> None:
    db = _open_db()
    audit = AuditService(db)
    storage = ObjectStorage()

    try:
        session = db.get(SessionRecord, UUID(session_id))
        if not session:
            logger.error("Session not found", extra={"session_id": session_id, "event_type": "pipeline"})
            return

        if start_at == "transcribe":
            _run_transcription(db, audit, storage, session)
            if session.status == SessionStatus.FAILED:
                return
            _run_role_identification(db, audit, session)
            if session.needs_review:
                return
            _run_summarization(db, audit, session)
            return

        if start_at == "summarize":
            _run_summarization(db, audit, session)
    except Exception as exc:
        db.rollback()
        session = db.get(SessionRecord, UUID(session_id))
        if session:
            session.status = SessionStatus.FAILED
            session.error_message = str(exc)
            db.commit()
            audit.log(session.id, "pipeline_failed", details={"error": str(exc)})
        logger.exception(
            "Pipeline failed",
            extra={"session_id": session_id, "event_type": "pipeline_failed"},
        )
        raise self.retry(exc=exc, countdown=30)
    finally:
        db.close()


def _run_transcription(db, audit, storage, session: SessionRecord) -> None:
    if session.raw_transcript and session.status in {
        SessionStatus.TRANSCRIBED,
        SessionStatus.IDENTIFYING_ROLES,
        SessionStatus.NEEDS_REVIEW,
        SessionStatus.SUMMARIZING,
        SessionStatus.COMPLETED,
    }:
        return

    session.status = SessionStatus.TRANSCRIBING
    db.commit()

    if not session.audio_uri:
        raise RuntimeError("Missing audio URI")

    audio_bytes = storage.download_audio(session.audio_uri)
    filename = session.audio_uri.rsplit("/", 1)[-1]
    segment_dicts = transcribe_audio(audio_bytes, filename)
    session.raw_transcript = {"segments": segment_dicts}
    session.status = SessionStatus.TRANSCRIBED
    db.commit()
    audit.log(session.id, "transcription_completed", details={"segment_count": len(segment_dicts)})


def _run_role_identification(db, audit, session: SessionRecord) -> None:
    if session.role_map and session.status in {SessionStatus.SUMMARIZING, SessionStatus.COMPLETED}:
        return

    session.status = SessionStatus.IDENTIFYING_ROLES
    db.commit()

    segments = session.raw_transcript["segments"]
    result = identify_speaker_roles(segments, prompt_options=session.prompt_options)
    session.role_map = result.role_map
    session.role_confidence = result.confidence
    session.role_reasoning = result.reasoning

    audit.log(
        session.id,
        "roles_identified",
        details={
            "confidence": result.confidence,
            "role_map": result.role_map,
        },
    )

    if result.confidence == "low":
        session.needs_review = True
        session.status = SessionStatus.NEEDS_REVIEW
        db.commit()
        audit.log(session.id, "manual_review_required", details={"confidence": "low"})
        return

    session.needs_review = False
    session.status = SessionStatus.TRANSCRIBED
    db.commit()


def _run_summarization(db, audit, session: SessionRecord) -> None:
    if session.summary and session.status == SessionStatus.COMPLETED:
        return

    if not session.role_map:
        raise RuntimeError("Role map required before summarization")

    purpose = (session.prompt_options or {}).get("purpose", "soap_note")
    if purpose not in {"soap_note", "summary", "clinical_document", "full_transcript_review"}:
        session.status = SessionStatus.COMPLETED
        db.commit()
        return

    session.status = SessionStatus.SUMMARIZING
    db.commit()

    segments = session.raw_transcript["segments"]
    output = generate_clinical_summary(segments, session.role_map, prompt_options=session.prompt_options)
    from app.models.schemas import ClinicalDocument, NarrativeSummary, SOAPSummary

    session.summary = None
    session.narrative_summary = None
    session.clinical_document = None
    if isinstance(output, NarrativeSummary):
        session.narrative_summary = output.model_dump()
        flag_count = len(output.flags)
    elif isinstance(output, ClinicalDocument):
        session.clinical_document = output.model_dump()
        flag_count = len(output.flags)
    else:
        session.summary = output.model_dump()
        flag_count = len(output.flags)
    session.status = SessionStatus.COMPLETED
    db.commit()

    audit.log(
        session.id,
        "summary_generated",
        details={"flag_count": flag_count},
    )
