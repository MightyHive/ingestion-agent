"""Resolve ingestion tenant context from credentials metadata + Secret Manager."""

from __future__ import annotations

from credentials.db import get_session
from credentials.exceptions import (
    ConnectionInactiveError,
    ConnectionNotFoundError,
    ConnectionProviderMismatchError,
)
from credentials.repository import ConnectionRepository
from credentials.schemas import ConnectionStatus
from credentials.secrets import get_connection_secret
from ingestion.auth.tenant_context import TenantContext


def resolve_for_run(
    *,
    tenant_id: str,
    connection_id: str,
    expected_platform: str,
) -> TenantContext:
    """Build a tenant context by resolving connection metadata + secret payload."""

    with get_session() as session:
        repo = ConnectionRepository(session)
        record = repo.get(tenant_id=tenant_id, connection_id=connection_id)
        if record is None:
            raise ConnectionNotFoundError(
                f"connection '{connection_id}' not found for tenant '{tenant_id}'"
            )
        if record.status != ConnectionStatus.ACTIVE:
            raise ConnectionInactiveError(
                f"connection '{connection_id}' is not active (status={record.status.value})"
            )
        if record.provider != expected_platform:
            raise ConnectionProviderMismatchError(
                f"connection '{connection_id}' provider '{record.provider}' "
                f"does not match manifest platform '{expected_platform}'"
            )

    context_payload = get_connection_secret(
        tenant_id=tenant_id,
        provider=record.provider,
        connection_id=connection_id,
    )
    base_tenant = TenantContext.resolve(tenant_id)
    return TenantContext(
        tenant_id=tenant_id,
        gcp_project=base_tenant.gcp_project,
        service_account=base_tenant.service_account,
        context=context_payload,
    )

