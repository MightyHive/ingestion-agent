"""Shared pytest fixtures for credentials repository tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from credentials.repository import ConnectionRepository
from credentials.tables import Base


@pytest.fixture
def session(tmp_path) -> Iterator[Session]:
    """Yield a fresh SQLite session bound to a temporary file."""

    db_path = tmp_path / "credentials_test.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def repository(session: Session) -> ConnectionRepository:
    """Provide a repository bound to the temporary session."""

    return ConnectionRepository(session)
