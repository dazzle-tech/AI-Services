"""SQLAlchemy models."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CaseStatus(str, enum.Enum):
    PENDING = "pending"
    INGESTING = "ingesting"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    IDENTIFYING_ROLES = "identifying_roles"
    NEEDS_REVIEW = "needs_review"
    EXTRACTING_TIMELINE = "extracting_timeline"
    VERIFYING_CHECKLIST = "verifying_checklist"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


class ChunkStatus(str, enum.Enum):
    PENDING = "pending"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    FAILED = "failed"


class CaseRecord(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, name="case_status"),
        default=CaseStatus.PENDING,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    procedure_type: Mapped[str] = mapped_column(String(256), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    scheduled_team: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ingest_mode: Mapped[str] = mapped_column(String(32), default="post_hoc", nullable=False)
    ingest_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    audio_uris: Mapped[list | None] = mapped_column(JSON, nullable=True)
    audio_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    speaker_registry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_transcript: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    role_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    role_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeline: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    medications: Mapped[list | None] = mapped_column(JSON, nullable=True)
    instrument_counts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    checklist_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prompt_options: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AudioChunkRecord(Base):
    """Tracks individual audio chunks for streaming OR cases."""

    __tablename__ = "audio_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_uri: Mapped[str] = mapped_column(Text, nullable=False)
    time_offset_seconds: Mapped[float] = mapped_column(nullable=False, default=0.0)
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[ChunkStatus] = mapped_column(
        Enum(ChunkStatus, name="chunk_status"),
        default=ChunkStatus.PENDING,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    transcribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
