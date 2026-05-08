"""Multi-tenant auth: TenantContext + service-account impersonation.

Each MDS client has its own GCP project. Their credentials live in
their own Secret Manager. MDS impersonates the client's SA via
``google.auth.impersonated_credentials`` to invoke their Cloud
Functions. Credentials never travel through MDS in the request payload.

See ``docs/architecture.md`` §5.
"""
