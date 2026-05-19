"""Credentials service orchestration helpers for API handlers.

This module coordinates metadata persistence and Secret Manager writes while
keeping HTTP concerns out of the credentials package internals.
"""

from __future__ import annotations

from credentials.db import get_session
from credentials.exceptions import ConnectionNotFoundError
from credentials.repository import ConnectionRepository
from credentials.schemas import ConnectionCreate, ConnectionRecord, ConnectionStatus
from credentials.secrets import (
    build_secret_id,
    rotate_connection_secret,
    store_connection_secret,
)


def upsert_connection(
    *,
    tenant_id: str,
    provider: str,
    connection_id: str,
    payload: dict | str,
    name: str | None = None,
) -> ConnectionRecord:
    """Create or update a tenant-scoped connection with secret persistence."""

    with get_session() as session:
        repo = ConnectionRepository(session)
        existing = repo.get(tenant_id=tenant_id, connection_id=connection_id)
        secret_id = build_secret_id(
            tenant_id=tenant_id,
            provider=provider,
            connection_id=connection_id,
        )

        if existing is None:
            store_connection_secret(
                tenant_id=tenant_id,
                provider=provider,
                connection_id=connection_id,
                payload=payload,
            )
            return repo.create_with_connection_id(
                connection_id=connection_id,
                data=ConnectionCreate(
                    tenant_id=tenant_id,
                    provider=provider,
                    secret_id=secret_id,
                    name=name,
                    status=ConnectionStatus.ACTIVE,
                ),
            )

        rotate_connection_secret(
            tenant_id=tenant_id,
            provider=provider,
            connection_id=connection_id,
            payload=payload,
        )
        return repo.update_metadata(
            tenant_id=tenant_id,
            connection_id=connection_id,
            name=name,
            secret_id=secret_id,
        )


def list_connections(
    *,
    tenant_id: str,
    status: ConnectionStatus | None = None,
) -> list[ConnectionRecord]:
    """List tenant-scoped connection metadata."""

    with get_session() as session:
        repo = ConnectionRepository(session)
        return repo.list_by_tenant(tenant_id=tenant_id, status=status)


def get_connection(*, tenant_id: str, connection_id: str) -> ConnectionRecord:
    """Return one connection or raise not-found for tenant mismatch/missing."""

    with get_session() as session:
        repo = ConnectionRepository(session)
        record = repo.get(tenant_id=tenant_id, connection_id=connection_id)
        if record is None:
            raise ConnectionNotFoundError(
                f"connection '{connection_id}' not found for tenant '{tenant_id}'"
            )
        return record


def update_connection_status(
    *,
    tenant_id: str,
    connection_id: str,
    status: ConnectionStatus,
) -> ConnectionRecord:
    """Update lifecycle status for one tenant-scoped connection."""

    with get_session() as session:
        repo = ConnectionRepository(session)
        return repo.update_status(
            tenant_id=tenant_id,
            connection_id=connection_id,
            status=status,
        )
