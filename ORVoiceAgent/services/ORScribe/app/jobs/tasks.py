"""Background pipeline tasks."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import configure_logging, get_logger
from app.db.models import AudioChunkRecord, CaseRecord, CaseStatus, ChunkStatus
from app.db.session import get_engine
from app.jobs.celery_app import celery_app
from app.ai.checklist_verification import verify_checklist
from app.ai.role_identification import identify_roles
from app.ai.timeline_extraction import extract_timeline
from app.services.audit_service import AuditService
from app.storage.s3 import ObjectStorage
from app.transcription import get_transcription_service
from app.transcription.speaker_registry import SpeakerRegistry

configure_logging()
logger = get_logger(__name__)


def _open_db() -> Session:
    from app.db import session as db_session

    if db_session.SessionLocal is None:
        db_session.get_engine()
    assert db_session.SessionLocal is not None
    return db_session.SessionLocal()


@celery_app.task(name="app.jobs.tasks.process_audio_chunk", bind=True, max_retries=2)
def process_audio_chunk(self, case_id: str, chunk_id: str) -> None:
    db = _open_db()
    audit = AuditService(db)
    storage = ObjectStorage()
    transcription = get_transcription_service()

    try:
        case = db.get(CaseRecord, UUID(case_id))
        chunk = db.get(AudioChunkRecord, UUID(chunk_id))
        if not case or not chunk:
            return

        chunk.status = ChunkStatus.TRANSCRIBING
        case.status = CaseStatus.TRANSCRIBING
        db.commit()

        audio_bytes = storage.download_audio(chunk.audio_uri)
        filename = chunk.audio_uri.rsplit("/", 1)[-1]
        raw_segments = transcription.transcribe_and_diarize(
            audio_bytes, filename, time_offset=chunk.time_offset_seconds
        )

        registry = SpeakerRegistry.from_dict(case.speaker_registry)
        local_labels = [s.speaker_label for s in raw_segments]
        mapped_segments = registry.map_chunk_segments(raw_segments, local_labels)
        case.speaker_registry = registry.to_dict()

        existing = case.raw_transcript or {"segments": []}
        new_segments = [
            {
                "speaker_label": s.speaker_label,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "text": s.text,
            }
            for s in mapped_segments
        ]
        existing["segments"].extend(new_segments)
        case.raw_transcript = existing

        chunk.status = ChunkStatus.TRANSCRIBED
        from datetime import datetime, timezone

        chunk.transcribed_at = datetime.now(timezone.utc)
        db.commit()

        audit.log(
            case.id,
            "chunk_transcribed",
            details={"chunk_index": chunk.chunk_index, "segment_count": len(new_segments)},
        )

        if _all_chunks_transcribed(db, case):
            case.status = CaseStatus.TRANSCRIBED
            db.commit()
            process_analysis_pipeline.delay(case_id)

    except Exception as exc:
        db.rollback()
        case = db.get(CaseRecord, UUID(case_id))
        chunk = db.get(AudioChunkRecord, UUID(chunk_id))
        if chunk:
            chunk.status = ChunkStatus.FAILED
        if case:
            case.status = CaseStatus.FAILED
            case.error_message = str(exc)
            db.commit()
            audit.log(case.id, "chunk_failed", details={"error": str(exc)})
        logger.exception("Chunk processing failed", extra={"case_id": case_id, "event_type": "chunk_failed"})
        raise self.retry(exc=exc, countdown=30)
    finally:
        db.close()


@celery_app.task(name="app.jobs.tasks.process_analysis_pipeline", bind=True, max_retries=2)
def process_analysis_pipeline(self, case_id: str, start_at: str = "roles") -> None:
    db = _open_db()
    audit = AuditService(db)

    try:
        case = db.get(CaseRecord, UUID(case_id))
        if not case or not case.raw_transcript:
            return

        segments = case.raw_transcript["segments"]
        prompt_options = case.prompt_options

        if start_at == "roles":
            _run_role_identification(db, audit, case, segments, prompt_options)
            if case.needs_review:
                return
            _run_downstream(db, audit, case, segments, prompt_options)
            _finalize_case(db, audit, case)
            return

        if start_at == "timeline":
            _run_downstream(db, audit, case, segments, prompt_options)
            _finalize_case(db, audit, case)
    except Exception as exc:
        db.rollback()
        case = db.get(CaseRecord, UUID(case_id))
        if case:
            case.status = CaseStatus.FAILED
            case.error_message = str(exc)
            db.commit()
            audit.log(case.id, "pipeline_failed", details={"error": str(exc)})
        logger.exception("Analysis pipeline failed", extra={"case_id": case_id, "event_type": "pipeline_failed"})
        raise self.retry(exc=exc, countdown=30)
    finally:
        db.close()


def _all_chunks_transcribed(db: Session, case: CaseRecord) -> bool:
    if not case.ingest_complete:
        return False
    chunks = db.query(AudioChunkRecord).filter(AudioChunkRecord.case_id == case.id).all()
    if not chunks:
        return False
    return all(c.status == ChunkStatus.TRANSCRIBED for c in chunks)


def _run_role_identification(db, audit, case: CaseRecord, segments: list, prompt_options=None) -> None:
    case.status = CaseStatus.IDENTIFYING_ROLES
    db.commit()

    result = identify_roles(segments, case.scheduled_team, prompt_options=prompt_options)
    case.role_map = {k: v.model_dump() for k, v in result.role_map.items()}
    case.role_reasoning = result.reasoning

    audit.log(
        case.id,
        "roles_identified",
        details={"role_map": case.role_map},
    )

    any_needs_review = any(v.get("needs_review") for v in case.role_map.values())
    if any_needs_review:
        case.needs_review = True
        case.status = CaseStatus.NEEDS_REVIEW
        db.commit()
        audit.log(case.id, "manual_review_required", details={"reason": "low_confidence_roles"})
        return

    case.needs_review = False
    db.commit()


def _run_downstream(db, audit, case: CaseRecord, segments: list, prompt_options=None) -> None:
    purpose = (prompt_options or {}).get("purpose", "full_transcript_review") if isinstance(prompt_options, dict) else getattr(prompt_options, "purpose", "full_transcript_review")
    # NOTE: soap_note / summary / clinical_document have no ORScribe summarizer.
    if purpose in {"timeline", "full_transcript_review"}:
        _run_timeline_extraction(db, audit, case, segments, prompt_options)
    if purpose in {"checklist_verification", "full_transcript_review"}:
        _run_checklist_verification(db, audit, case, segments, prompt_options)


def _run_timeline_extraction(db, audit, case: CaseRecord, segments: list, prompt_options=None) -> None:
    case.status = CaseStatus.EXTRACTING_TIMELINE
    db.commit()

    result = extract_timeline(segments, case.role_map or {}, prompt_options=prompt_options)
    case.timeline = {"events": [e.model_dump() for e in result.events]}
    case.medications = [m.model_dump() for m in result.medications_administered]
    case.instrument_counts = [c.model_dump() for c in result.instrument_counts]
    db.commit()

    audit.log(
        case.id,
        "timeline_extracted",
        details={
            "event_count": len(result.events),
            "medication_count": len(result.medications_administered),
        },
    )


def _run_checklist_verification(db, audit, case: CaseRecord, segments: list, prompt_options=None) -> None:
    case.status = CaseStatus.VERIFYING_CHECKLIST
    db.commit()

    result = verify_checklist(segments, case.role_map or {}, prompt_options=prompt_options)
    case.checklist_result = result.model_dump()
    db.commit()

    audit.log(
        case.id,
        "checklist_verified",
        details={
            "sign_in_complete": result.sign_in.completed,
            "time_out_complete": result.time_out.completed,
            "sign_out_complete": result.sign_out.completed,
        },
    )


def _finalize_case(db, audit, case: CaseRecord) -> None:
    case.status = CaseStatus.FINALIZING
    db.commit()

    case.status = CaseStatus.COMPLETED
    db.commit()

    audit.log(case.id, "case_finalized", details={"status": "completed"})
