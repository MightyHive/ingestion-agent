"""SQLAlchemy table definitions for credentials metadata.

Tokens must never be persisted here — only metadata and secret references.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ConnectionRow(Base):
    __tablename__ = "connections"
    __table_args__ = (
        Index("ix_connections_tenant_id", "tenant_id"),
        Index("ix_connections_tenant_status", "tenant_id", "status"),
        CheckConstraint(
            "status IN ('active', 'inactive', 'revoked')",
            name="ck_connections_status",
        ),
    )

    connection_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    secret_id: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
