"""Database session management."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Base

_engine: Engine | None = None
SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine, SessionLocal
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
        SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    return _engine


def reset_engine() -> None:
    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal = None


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        get_engine()
    assert SessionLocal is not None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
