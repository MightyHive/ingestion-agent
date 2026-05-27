"""SQLAlchemy engine and session for credentials metadata."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB_PATH = _REPO_ROOT / "mds_credentials.db"


def _resolve_database_url() -> str:
    direct = os.getenv("DATABASE_URL")
    if direct:
        return direct
    db_path = os.getenv("MDS_DB_PATH")
    if db_path:
        return f"sqlite:///{Path(db_path).expanduser()}"
    return f"sqlite:///{_DEFAULT_DB_PATH}"


DATABASE_URL = _resolve_database_url()

engine = create_engine(DATABASE_URL, future=True)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def init_db() -> None:
    from credentials.tables import Base
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
