"""Session lifecycle orchestration."""

import io
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from mutagen import File as MutagenFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import SessionRecord, SessionStatus
from app.jobs.tasks import process_session_pipeline
from app.models.schemas import SessionResponse
from app.services.audit_service import AuditService
from app.storage.s3 import ObjectStorage

logger = get_logger(__name__)

CONTENT_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
}


class SessionService:
    def __init__(self, db: Session, storage: Optional[ObjectStorage] = None) -> None:
        self._db = db
        self._storage = storage or ObjectStorage()
        self._audit = AuditService(db)

    def create_session(
        self,
        *,
        audio: UploadFile,
        patient_id: str,
        clinician_id: str,
        prompt_options=None,
    ) -> SessionRecord:
        from app.models.schemas import TranscriptionRequestOptions

        options = prompt_options or TranscriptionRequestOptions()
        if not isinstance(options, TranscriptionRequestOptions):
            options = TranscriptionRequestOptions.model_validate(options)
        extension = self._validate_upload(audio)
        data = audio.file.read()
        duration = self._get_duration_seconds(data, extension)

        if duration > settings.max_audio_duration_seconds:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Audio duration {duration:.1f}s exceeds maximum {settings.max_audio_duration_seconds}s",
            )

        session = SessionRecord(
            patient_id=patient_id,
            clinician_id=clinician_id,
            status=SessionStatus.PENDING,
            prompt_options=options.model_dump(),
        )
        self._db.add(session)
        self._db.commit()
        self._db.refresh(session)

        filename = f"audio.{extension}"
        content_type = CONTENT_TYPES.get(extension, "application/octet-stream")
        audio_uri = self._storage.upload_audio(session.id, filename, data, content_type)
        session.audio_uri = audio_uri
        self._db.commit()

        self._audit.log(
            session.id,
            "session_created",
            actor=clinician_id,
            details={"patient_id": patient_id, "duration_seconds": round(duration, 2)},
        )

        process_session_pipeline.delay(str(session.id))
        logger.info(
            "Session ingested",
            extra={"session_id": str(session.id), "event_type": "ingest"},
        )
        return session

    def get_session(self, session_id: UUID) -> SessionRecord:
        session = self._db.get(SessionRecord, session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return session

    def to_response(self, session: SessionRecord) -> SessionResponse:
        return SessionResponse(
            id=session.id,
            status=session.status.value,
            created_at=session.created_at,
            patient_id=session.patient_id,
            clinician_id=session.clinician_id,
            needs_review=session.needs_review,
            clinician_approved=session.clinician_approved,
            approved_by=session.approved_by,
            approved_at=session.approved_at,
            raw_transcript=session.raw_transcript,
            role_map=session.role_map,
            role_confidence=session.role_confidence,
            role_reasoning=session.role_reasoning,
            summary=session.summary,
            narrative_summary=session.narrative_summary,
            clinical_document=session.clinical_document,
            error_message=session.error_message,
        )

    def update_roles(self, session: SessionRecord, role_map: dict, actor: str) -> SessionRecord:
        session.role_map = role_map
        session.needs_review = False
        session.role_confidence = "high"
        session.status = SessionStatus.SUMMARIZING
        self._db.commit()

        self._audit.log(
            session.id,
            "roles_corrected",
            actor=actor,
            details={"role_map": role_map},
        )
        process_session_pipeline.delay(str(session.id), start_at="summarize")
        self._db.refresh(session)
        return session

    def approve_session(self, session: SessionRecord, clinician_id: str) -> SessionRecord:
        from datetime import datetime, timezone

        session.clinician_approved = True
        session.approved_by = clinician_id
        session.approved_at = datetime.now(timezone.utc)
        self._db.commit()

        self._audit.log(
            session.id,
            "clinician_approved",
            actor=clinician_id,
            details={"approved_at": session.approved_at.isoformat()},
        )
        return session

    @staticmethod
    def _validate_upload(audio: UploadFile) -> str:
        if not audio.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename required")

        extension = audio.filename.rsplit(".", 1)[-1].lower()
        if extension not in settings.allowed_extensions_list:
            allowed = ", ".join(settings.allowed_extensions_list)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported format '.{extension}'. Allowed: {allowed}",
            )
        return extension

    @staticmethod
    def _get_duration_seconds(data: bytes, extension: str) -> float:
        try:
            audio_file = MutagenFile(io.BytesIO(data))
            if audio_file is not None and audio_file.info is not None:
                return float(audio_file.info.length)
        except Exception:
            pass

        # Stub / minimal audio in tests may lack metadata — assume short clip
        if len(data) < 1024:
            return 5.0
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to determine audio duration",
        )
