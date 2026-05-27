"""Credentials service: orchestrates metadata persistence and secret writes."""

from __future__ import annotations

from credentials.db import get_session
from credentials.exceptions import (
    ConnectionInactiveError,
    ConnectionNotFoundError,
    InvalidStatusTransitionError,
)
from credentials.lifecycle import (
    connection_allows_secret_write,
    validate_status_transition,
)
from credentials.repository import ConnectionRepository
from credentials.schemas import ConnectionCreate, ConnectionRecord, ConnectionStatus
from credentials.secrets import (
    build_secret_id,
    check_secret_exists,
    get_connection_secret,
    revoke_connection_secret,
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
    with get_session() as session:
        repo = ConnectionRepository(session)
        existing = repo.get(tenant_id=tenant_id, connection_id=connection_id)
        secret_id = build_secret_id(
            tenant_id=tenant_id,
            provider=provider,
            connection_id=connection_id,
        )

        if existing is not None and not connection_allows_secret_write(existing.status):
            raise ConnectionInactiveError(
                f"connection '{connection_id}' is not active (status={existing.status.value})"
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

        # Merge non-empty submitted fields onto the existing secret so that
        # editing only one field (e.g. ad_account_id) does not silently drop
        # the others (e.g. access_token).
        merged_payload = payload
        if isinstance(payload, dict):
            try:
                existing_payload = get_connection_secret(
                    tenant_id=tenant_id,
                    provider=provider,
                    connection_id=connection_id,
                )
                merged = dict(existing_payload)
                for k, v in payload.items():
                    if v is not None and str(v).strip():
                        merged[k] = v
                merged_payload = merged
            except Exception:  # noqa: BLE001 — unreadable secret → use submitted payload as-is
                pass

        rotate_connection_secret(
            tenant_id=tenant_id,
            provider=provider,
            connection_id=connection_id,
            payload=merged_payload,
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
    with get_session() as session:
        repo = ConnectionRepository(session)
        records = repo.list_by_tenant(tenant_id=tenant_id, status=status)

    # Lazy health check: verify each active connection's secret still exists in SM.
    # If not found → delete the DB record so stale entries don't linger.
    result = []
    for record in records:
        if record.status == ConnectionStatus.ACTIVE:
            try:
                exists = check_secret_exists(
                    tenant_id=tenant_id,
                    provider=record.provider,
                    connection_id=record.connection_id,
                )
            except Exception:  # noqa: BLE001 — SM unavailable → assume intact
                exists = True
            if not exists:
                with get_session() as session:
                    repo = ConnectionRepository(session)
                    try:
                        repo.delete(tenant_id=tenant_id, connection_id=record.connection_id)
                    except Exception:  # noqa: BLE001 — already gone, ignore
                        pass
                continue
        result.append(record)
    return result


def get_connection(*, tenant_id: str, connection_id: str) -> ConnectionRecord:
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
    with get_session() as session:
        repo = ConnectionRepository(session)
        existing = repo.get(tenant_id=tenant_id, connection_id=connection_id)
        if existing is None:
            raise ConnectionNotFoundError(
                f"connection '{connection_id}' not found for tenant '{tenant_id}'"
            )

        validate_status_transition(existing.status, status)

        if status == ConnectionStatus.REVOKED:
            revoke_connection_secret(
                tenant_id=tenant_id,
                provider=existing.provider,
                connection_id=connection_id,
            )

        return repo.update_status(
            tenant_id=tenant_id,
            connection_id=connection_id,
            status=status,
        )
