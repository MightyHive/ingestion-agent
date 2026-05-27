"""DELETED — this module was dead code and has been retired.

The previous implementation (`resolve_for_run`) instantiated
``ingestion.auth.tenant_context.TenantContext`` with keyword arguments
that the dataclass does not accept (``connection_id``, ``provider``,
``secret_project_id``, ``secret_id``). It would raise ``TypeError`` on
the first real call.

It was never wired into the request path: in the current architecture the
Cloud Function resolves its own secrets from Secret Manager using its own
SA — the backend only forwards ``connection_id`` as part of the CF
payload (see ``src/ingestion/dispatcher/http.py::_build_payload``). The
backend never needs the credential payload in-process.

This stub is kept as an empty placeholder only because the sandbox cannot
delete the file. Run on your Mac to fully remove it:

    rm src/credentials/resolver.py

The export was removed from ``src/credentials/__init__.py`` at the same
time.
"""
