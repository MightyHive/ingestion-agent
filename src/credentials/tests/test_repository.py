"""Unit tests for the tenant-scoped credentials repository."""

from __future__ import annotations

from credentials.exceptions import ConnectionNotFoundError
from credentials.schemas import ConnectionCreate, ConnectionStatus


def test_create_and_get_round_trip(repository) -> None:
    """A created row can be fetched by the same tenant and id."""

    created = repository.create(
        ConnectionCreate(
            tenant_id="tenant_a",
            provider="meta",
            secret_id="projects/p1/secrets/s1",
            name="Meta primary",
        )
    )

    found = repository.get("tenant_a", created.connection_id)
    assert found is not None
    assert found.connection_id == created.connection_id
    assert found.provider == "meta"
    assert found.status == ConnectionStatus.ACTIVE


def test_list_by_tenant_is_isolated(repository) -> None:
    """Each tenant sees only their own connections."""

    repository.create(
        ConnectionCreate(
            tenant_id="tenant_a",
            provider="meta",
            secret_id="projects/p1/secrets/meta-a",
        )
    )
    repository.create(
        ConnectionCreate(
            tenant_id="tenant_b",
            provider="dv360",
            secret_id="projects/p2/secrets/dv360-b",
        )
    )

    tenant_a_rows = repository.list_by_tenant("tenant_a")
    tenant_b_rows = repository.list_by_tenant("tenant_b")
    assert len(tenant_a_rows) == 1
    assert len(tenant_b_rows) == 1
    assert tenant_a_rows[0].tenant_id == "tenant_a"
    assert tenant_b_rows[0].tenant_id == "tenant_b"


def test_get_with_wrong_tenant_returns_none(repository) -> None:
    """Reading with another tenant id does not leak records."""

    created = repository.create(
        ConnectionCreate(
            tenant_id="tenant_a",
            provider="meta",
            secret_id="projects/p1/secrets/s1",
        )
    )
    assert repository.get("tenant_b", created.connection_id) is None


def test_update_status_is_tenant_scoped(repository) -> None:
    """Status updates require the matching tenant."""

    created = repository.create(
        ConnectionCreate(
            tenant_id="tenant_a",
            provider="meta",
            secret_id="projects/p1/secrets/s1",
        )
    )

    updated = repository.update_status(
        tenant_id="tenant_a",
        connection_id=created.connection_id,
        status=ConnectionStatus.INACTIVE,
    )
    assert updated.status == ConnectionStatus.INACTIVE

    try:
        repository.update_status(
            tenant_id="tenant_b",
            connection_id=created.connection_id,
            status=ConnectionStatus.REVOKED,
        )
        raise AssertionError("expected ConnectionNotFoundError")
    except ConnectionNotFoundError:
        pass

    same_row = repository.get("tenant_a", created.connection_id)
    assert same_row is not None
    assert same_row.status == ConnectionStatus.INACTIVE


def test_list_by_tenant_with_status_filter(repository) -> None:
    """Status filter returns only matching rows for the tenant."""

    active = repository.create(
        ConnectionCreate(
            tenant_id="tenant_a",
            provider="meta",
            secret_id="projects/p1/secrets/s1",
            status=ConnectionStatus.ACTIVE,
        )
    )
    repository.create(
        ConnectionCreate(
            tenant_id="tenant_a",
            provider="dv360",
            secret_id="projects/p1/secrets/s2",
            status=ConnectionStatus.INACTIVE,
        )
    )

    only_active = repository.list_by_tenant(
        "tenant_a",
        status=ConnectionStatus.ACTIVE,
    )
    assert len(only_active) == 1
    assert only_active[0].connection_id == active.connection_id
