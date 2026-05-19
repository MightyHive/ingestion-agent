"""SQLAlchemy table definitions for credentials metadata.

Only connection metadata is stored here. Secret payloads (tokens, refresh
tokens, OAuth grants) must never be persisted in this table.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for credentials tables."""


class ConnectionRow(Base):
    """Row model for tenant-scoped credential connections."""

    __tablename__ = "connections"
    __table_args__ = (
        # Tenant-first indexing makes list/read operations explicit and safe.
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
