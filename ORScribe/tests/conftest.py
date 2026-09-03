"""Pytest configuration."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import reload_settings
from app.db.models import Base
from app.db.session import reset_engine


@pytest.fixture(autouse=True)
def test_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("USE_LLM_STUB", "true")
    monkeypatch.setenv("TRANSCRIPTION_BACKEND", "stub")
    monkeypatch.setenv("S3_ACCESS_KEY", "test")
    monkeypatch.setenv("S3_SECRET_KEY", "test")
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    reload_settings()
    reset_engine()


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
