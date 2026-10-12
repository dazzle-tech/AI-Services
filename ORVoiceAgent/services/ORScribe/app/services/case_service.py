"""Case lifecycle orchestration."""

import io
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from mutagen import File as MutagenFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import AudioChunkRecord, CaseRecord, CaseStatus, ChunkStatus
from app.jobs.tasks import process_analysis_pipeline, process_audio_chunk
from app.models.schemas import CaseResponse
from app.services.audit_service import AuditService
from app.storage.s3 import ObjectStorage

logger = get_logger(__name__)

CONTENT_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
}


class CaseService:
    def __init__(self, db: Session, storage: Optional[ObjectStorage] = None) -> None:
        self._db = db
        self._storage = storage or ObjectStorage()
        self._audit = AuditService(db)

    def create_case(
        self,
        *,
        procedure_type: str,
        staff_id: str,
        scheduled_team: dict | None = None,
        ingest_mode: str = "post_hoc",
        audio: UploadFile | None = None,
        prompt_options=None,
    ) -> CaseRecord:
        from app.models.schemas import TranscriptionRequestOptions

        options = prompt_options or TranscriptionRequestOptions()
        if not isinstance(options, TranscriptionRequestOptions):
            options = TranscriptionRequestOptions.model_validate(options)

        case = CaseRecord(
            procedure_type=procedure_type,
            created_by=staff_id,
            scheduled_team=scheduled_team,
            ingest_mode=ingest_mode,
            prompt_options=options.model_dump(),
            status=CaseStatus.PENDING if ingest_mode == "streaming" else CaseStatus.INGESTING,
            ingest_complete=ingest_mode == "post_hoc" and audio is None,
            audio_uris=[],
            speaker_registry={},
        )
        self._db.add(case)
        self._db.commit()
        self._db.refresh(case)

        self._audit.log(
            case.id,
            "case_created",
            actor=staff_id,
            details={
                "procedure_type": procedure_type,
                "ingest_mode": ingest_mode,
            },
        )

        if audio is not None:
            self.add_audio_chunk(
                case=case,
                audio=audio,
                chunk_index=0,
                is_final=True,
                staff_id=staff_id,
            )
        elif ingest_mode == "streaming":
            case.status = CaseStatus.INGESTING
            self._db.commit()

        logger.info("Case created", extra={"case_id": str(case.id), "event_type": "ingest"})
        return case

    def add_audio_chunk(
        self,
        *,
        case: CaseRecord,
        audio: UploadFile,
        chunk_index: int,
        is_final: bool,
        staff_id: str,
    ) -> AudioChunkRecord:
        if case.ingest_complete:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Case ingest is already complete",
            )

        extension = self._validate_upload(audio)
        data = audio.file.read()
        duration = self._get_duration_seconds(data, extension)

        if duration > settings.max_audio_duration_seconds:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Chunk duration {duration:.1f}s exceeds maximum",
            )

        existing = (
            self._db.query(AudioChunkRecord)
            .filter(
                AudioChunkRecord.case_id == case.id,
                AudioChunkRecord.chunk_index == chunk_index,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Chunk index {chunk_index} already exists",
            )

        time_offset = self._compute_time_offset(case.id)
        filename = f"chunk_{chunk_index:04d}.{extension}"
        content_type = CONTENT_TYPES.get(extension, "application/octet-stream")
        audio_uri = self._storage.upload_audio(case.id, filename, data, content_type)

        chunk = AudioChunkRecord(
            case_id=case.id,
            chunk_index=chunk_index,
            audio_uri=audio_uri,
            time_offset_seconds=time_offset,
            duration_seconds=duration,
            status=ChunkStatus.PENDING,
        )
        self._db.add(chunk)

        uris = list(case.audio_uris or [])
        uris.append(audio_uri)
        case.audio_uris = uris
        case.status = CaseStatus.INGESTING
        if is_final:
            case.ingest_complete = True
        self._db.commit()
        self._db.refresh(chunk)

        self._audit.log(
            case.id,
            "audio_chunk_received",
            actor=staff_id,
            details={
                "chunk_index": chunk_index,
                "duration_seconds": round(duration, 2),
                "is_final": is_final,
            },
        )

        process_audio_chunk.delay(str(case.id), str(chunk.id))

        if is_final:
            self._audit.log(case.id, "ingest_complete", actor=staff_id)

        return chunk

    def get_case(self, case_id: UUID) -> CaseRecord:
        case = self._db.get(CaseRecord, case_id)
        if not case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
        return case

    def to_response(self, case: CaseRecord) -> CaseResponse:
        return CaseResponse(
            id=case.id,
            status=case.status.value,
            created_at=case.created_at,
            procedure_type=case.procedure_type,
            created_by=case.created_by,
            scheduled_team=case.scheduled_team,
            ingest_mode=case.ingest_mode,
            ingest_complete=case.ingest_complete,
            needs_review=case.needs_review,
            approved_by=case.approved_by,
            approved_at=case.approved_at,
            role_map=case.role_map,
            role_reasoning=case.role_reasoning,
            timeline=case.timeline,
            medications=case.medications,
            instrument_counts=case.instrument_counts,
            checklist_result=case.checklist_result,
            error_message=case.error_message,
        )

    def update_roles(self, case: CaseRecord, role_map: dict, actor: str) -> CaseRecord:
        normalized = {
            speaker: {"role": role, "confidence": "high", "needs_review": False}
            for speaker, role in role_map.items()
        }
        case.role_map = normalized
        case.needs_review = False
        case.status = CaseStatus.EXTRACTING_TIMELINE
        self._db.commit()

        self._audit.log(
            case.id,
            "roles_corrected",
            actor=actor,
            details={"role_map": role_map},
        )
        process_analysis_pipeline.delay(str(case.id), start_at="timeline")
        self._db.refresh(case)
        return case

    def approve_case(self, case: CaseRecord, user_id: str) -> CaseRecord:
        from datetime import datetime, timezone

        if case.status != CaseStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Case must be completed before approval",
            )

        case.approved_by = user_id
        case.approved_at = datetime.now(timezone.utc)
        self._db.commit()

        self._audit.log(
            case.id,
            "case_approved",
            actor=user_id,
            details={"approved_at": case.approved_at.isoformat()},
        )
        return case

    def _compute_time_offset(self, case_id: UUID) -> float:
        chunks = (
            self._db.query(AudioChunkRecord)
            .filter(AudioChunkRecord.case_id == case_id)
            .order_by(AudioChunkRecord.chunk_index)
            .all()
        )
        return sum(c.duration_seconds or 0 for c in chunks)

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
        if len(data) < 1024:
            return 5.0
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to determine audio duration",
        )
