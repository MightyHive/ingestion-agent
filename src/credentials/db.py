"""
This module centralizes SQLAlchemy engine/session creation and keeps the
repository layer independent from database URL details.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# repo/src/credentials/db.py -> parents[2] is repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB_PATH = _REPO_ROOT / "mds_credentials.db"


def _resolve_database_url() -> str:
    """Resolve database URL from env vars with SQLite fallback.

    Resolution order:
    1. DATABASE_URL
    2. MDS_DB_PATH (translated to sqlite:/// URL)
    3. <repo>/mds_credentials.db
    """

    direct = os.getenv("DATABASE_URL")
    if direct:
        return direct

    db_path = os.getenv("MDS_DB_PATH")
    if db_path:
        return f"sqlite:///{Path(db_path).expanduser()}"

    return f"sqlite:///{_DEFAULT_DB_PATH}"


DATABASE_URL = _resolve_database_url()

# A single process-wide engine keeps database setup simple.
engine = create_engine(DATABASE_URL, future=True)

# expire_on_commit=False lets repository return objects without reloading.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def init_db() -> None:
    """Create credentials tables if they do not exist."""

    # Imported lazily to avoid circular imports during module initialization.
    from credentials.tables import Base

    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a database session and always close it."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
