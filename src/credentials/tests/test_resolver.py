"""Unit tests for credentials.resolver.resolve_for_run."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy.orm import Session

import credentials.resolver as resolver_module
from credentials.exceptions import (
    ConnectionInactiveError,
    ConnectionNotFoundError,
    ConnectionProviderMismatchError,
)
from credentials.repository import ConnectionRepository
from credentials.schemas import ConnectionCreate, ConnectionStatus
from ingestion.auth.tenant_context import TenantContext


def _patch_session(monkeypatch: pytest.MonkeyPatch, session: Session) -> None:
    @contextmanager
    def _get_session():
        yield session

    monkeypatch.setattr(resolver_module, "get_session", _get_session)


def test_resolve_for_run_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _patch_session(monkeypatch, session)
    repo = ConnectionRepository(session)
    repo.create_with_connection_id(
        connection_id="conn-1",
        data=ConnectionCreate(
            tenant_id="tenant-a",
            provider="meta",
            secret_id="tenant-a-meta-conn-1",
            status=ConnectionStatus.ACTIVE,
        ),
    )
    monkeypatch.setattr(
        resolver_module,
        "get_connection_secret",
        lambda tenant_id, provider, connection_id: {"access_token": "tok-1"},
    )
    monkeypatch.setattr(
        resolver_module.TenantContext,
        "resolve",
        classmethod(
            lambda cls, tenant_id: TenantContext(
                tenant_id=tenant_id,
                gcp_project="monks-mds-dev",
                service_account="runner@monks-mds-dev.iam.gserviceaccount.com",
                context={"ignored": True},
            )
        ),
    )

    resolved = resolver_module.resolve_for_run(
        tenant_id="tenant-a",
        connection_id="conn-1",
        expected_platform="meta",
    )
    assert resolved.tenant_id == "tenant-a"
    assert resolved.gcp_project == "monks-mds-dev"
    assert resolved.context == {"access_token": "tok-1"}


def test_resolve_for_run_not_found(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _patch_session(monkeypatch, session)
    with pytest.raises(ConnectionNotFoundError):
        resolver_module.resolve_for_run(
            tenant_id="tenant-a",
            connection_id="missing",
            expected_platform="meta",
        )


def test_resolve_for_run_inactive(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _patch_session(monkeypatch, session)
    repo = ConnectionRepository(session)
    repo.create_with_connection_id(
        connection_id="conn-2",
        data=ConnectionCreate(
            tenant_id="tenant-a",
            provider="meta",
            secret_id="tenant-a-meta-conn-2",
            status=ConnectionStatus.INACTIVE,
        ),
    )
    with pytest.raises(ConnectionInactiveError):
        resolver_module.resolve_for_run(
            tenant_id="tenant-a",
            connection_id="conn-2",
            expected_platform="meta",
        )


def test_resolve_for_run_provider_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _patch_session(monkeypatch, session)
    repo = ConnectionRepository(session)
    repo.create_with_connection_id(
        connection_id="conn-3",
        data=ConnectionCreate(
            tenant_id="tenant-a",
            provider="meta",
            secret_id="tenant-a-meta-conn-3",
            status=ConnectionStatus.ACTIVE,
        ),
    )
    with pytest.raises(ConnectionProviderMismatchError):
        resolver_module.resolve_for_run(
            tenant_id="tenant-a",
            connection_id="conn-3",
            expected_platform="dv360",
        )

