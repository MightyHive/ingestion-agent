"""Unit tests for credentials service orchestration."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy.orm import Session

from credentials.exceptions import (
    ConnectionInactiveError,
    InvalidStatusTransitionError,
)
from credentials.schemas import ConnectionCreate, ConnectionStatus
from credentials import service as credentials_service


@pytest.fixture(autouse=True)
def _patch_get_session(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def _get_session():
        yield session

    monkeypatch.setattr(credentials_service, "get_session", _get_session)


def test_upsert_blocked_when_inactive(repository, monkeypatch: pytest.MonkeyPatch) -> None:
    record = repository.create_with_connection_id(
        connection_id="conn-inactive",
        data=ConnectionCreate(
            tenant_id="tenant-a",
            provider="meta",
            secret_id="tenant-a-meta-conn-inactive",
            status=ConnectionStatus.INACTIVE,
        ),
    )

    def _fail_store(**kwargs):
        raise AssertionError("secret write should not run for inactive connection")

    monkeypatch.setattr(credentials_service, "store_connection_secret", _fail_store)
    monkeypatch.setattr(credentials_service, "rotate_connection_secret", _fail_store)

    with pytest.raises(ConnectionInactiveError):
        credentials_service.upsert_connection(
            tenant_id=record.tenant_id,
            provider=record.provider,
            connection_id=record.connection_id,
            payload={"access_token": "new"},
        )


def test_update_status_revoke_calls_secret_revoke(
    repository, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = repository.create_with_connection_id(
        connection_id="conn-revoke",
        data=ConnectionCreate(
            tenant_id="tenant-a",
            provider="meta",
            secret_id="tenant-a-meta-conn-revoke",
        ),
    )
    calls: list[tuple[str, str, str]] = []

    def _revoke(**kwargs):
        calls.append(
            (kwargs["tenant_id"], kwargs["provider"], kwargs["connection_id"])
        )
        return 2

    monkeypatch.setattr(credentials_service, "revoke_connection_secret", _revoke)

    updated = credentials_service.update_connection_status(
        tenant_id=record.tenant_id,
        connection_id=record.connection_id,
        status=ConnectionStatus.REVOKED,
    )
    assert updated.status == ConnectionStatus.REVOKED
    assert calls == [("tenant-a", "meta", "conn-revoke")]


def test_update_status_rejects_revoked_to_active(repository) -> None:
    record = repository.create_with_connection_id(
        connection_id="conn-done",
        data=ConnectionCreate(
            tenant_id="tenant-a",
            provider="meta",
            secret_id="tenant-a-meta-conn-done",
            status=ConnectionStatus.REVOKED,
        ),
    )

    with pytest.raises(InvalidStatusTransitionError):
        credentials_service.update_connection_status(
            tenant_id=record.tenant_id,
            connection_id=record.connection_id,
            status=ConnectionStatus.ACTIVE,
        )
