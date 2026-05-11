"""Multi-tenant auth: TenantContext + service-account impersonation.

Each MDS client has its own GCP project. Their credentials live in
their own Secret Manager. MDS impersonates the client's SA via
``google.auth.impersonated_credentials`` to invoke their Cloud
Functions. Credentials never travel through MDS in the request payload.

Phase 2 ships a JSON-file stub of :class:`TenantContext`. Phase 5
swaps the stub for the real impersonation flow.

See ``docs/architecture.md`` §5.
"""

from ingestion.auth.tenant_context import (
    DEFAULT_TENANTS_PATH,
    MissingContextKeyError,
    TenantConfigError,
    TenantContext,
    UnknownTenantError,
    set_loader_for_testing,
)

__all__ = [
    "DEFAULT_TENANTS_PATH",
    "MissingContextKeyError",
    "TenantConfigError",
    "TenantContext",
    "UnknownTenantError",
    "set_loader_for_testing",
]
