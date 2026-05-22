"""connector_runner — invokes the connector via the dispatcher.

This is where Phase 2 still differs significantly from Phase 5:

* Phase 2: ``LocalBackend`` imports the connector module from
  ``connectors-library/`` and calls ``fetch(params, context)``
  directly.
* Phase 5: ``HTTPBackend`` POSTs to the deployed Cloud Function with an
  impersonated id_token; the same connector code runs inside GCP.

The node is identical in both phases — only the dispatcher differs.

Output payload (``NodeLOL.data``) on OK::

    {
        "manifest_id":  str,
        "tenant_id":    str,
        "connector":    {              # ConnectorResponse → dict
            "status":      str,
            "code":        int,
            "records":     Any,
            "meta":        dict,
            "errors":      list[str],
            "diagnostics": dict,
        }
    }

WARN is emitted when the connector returns ``status='partial'`` or has
non-empty ``errors``; the run continues to ``format_response`` because
partial data is often still useful for the frontend.
"""

from __future__ import annotations

from typing import Any

from ingestion.auth.tenant_context import (
    MissingContextKeyError,
    TenantConfigError,
    TenantContext,
    UnknownTenantError,
)
from ingestion.dispatcher.base import (
    BackendError,
    ConnectorDispatcher,
    ConnectorResponse,
)
from ingestion.lol import NodeLOL

NODE_NAME = "connector_runner"


def _resolve_tenant(tenant_id: str) -> tuple[TenantContext | None, str | None]:
    """Resolve the tenant or return a single-line error string."""
    try:
        return TenantContext.resolve(tenant_id), None
    except UnknownTenantError as exc:
        return None, str(exc)
    except TenantConfigError as exc:
        return None, f"tenant config error: {exc}"


def _response_to_dict(resp: ConnectorResponse) -> dict[str, Any]:
    return {
        "status": resp.status,
        "code": resp.code,
        "records": resp.records,
        "meta": resp.meta,
        "errors": resp.errors,
        "diagnostics": resp.diagnostics,
    }


def run(
    manifest: dict[str, Any],
    params: dict[str, Any],
    tenant_id: str,
    *,
    dispatcher: ConnectorDispatcher | None = None,
) -> NodeLOL:
    """Pure function: invoke the connector for a manifest + tenant.

    The graph wrapper around this function is the LangGraph node. Tests
    can call ``run`` directly with a stub dispatcher.
    """
    tenant, err = _resolve_tenant(tenant_id)
    if err is not None:
        return NodeLOL.err(
            NODE_NAME,
            f"could not resolve tenant '{tenant_id}'",
            [err],
            data={"manifest_id": manifest.get("id"), "tenant_id": tenant_id},
        )

    disp = dispatcher if dispatcher is not None else ConnectorDispatcher()
    try:
        response = disp.invoke(manifest, params, tenant)
    except MissingContextKeyError as exc:
        return NodeLOL.err(
            NODE_NAME,
            f"tenant '{tenant_id}' missing required context keys",
            [str(exc)],
            data={"manifest_id": manifest.get("id"), "tenant_id": tenant_id},
        )
    except BackendError as exc:
        return NodeLOL.err(
            NODE_NAME,
            f"backend failed for manifest '{manifest.get('id')}'",
            [str(exc)],
            data={"manifest_id": manifest.get("id"), "tenant_id": tenant_id},
        )

    response_payload = _response_to_dict(response)
    payload = {
        "manifest_id": manifest.get("id"),
        "tenant_id": tenant_id,
        "connector": response_payload,
    }

    if response.status == "error" or (response.errors and response.status != "partial"):
        return NodeLOL.err(
            NODE_NAME,
            f"connector reported errors ({len(response.errors)}): "
            f"{response.errors[0] if response.errors else 'unknown'}",
            list(response.errors),
            data=payload,
        )

    if response.status == "partial" or response.errors:
        return NodeLOL.warn(
            NODE_NAME,
            f"connector returned partial data ({len(response.errors)} non-fatal error(s))",
            data=payload,
            errors=list(response.errors),
        )

    return NodeLOL.ok(
        NODE_NAME,
        reason=(
            f"connector '{manifest.get('id')}' returned status={response.status} "
            f"code={response.code}"
        ),
        data=payload,
    )


# ---------------------------------------------------------------------------
# LangGraph node wrapper
# ---------------------------------------------------------------------------

def node(state: dict[str, Any]) -> dict[str, Any]:
    manifest = state.get("manifest")
    if not manifest:
        lol = NodeLOL.err(
            NODE_NAME,
            "manifest missing in state — validator must run first",
            ["state.manifest is None"],
        )
        return {
            "node_results": [lol.model_dump()],
            "last_status": lol.status,
            "final_error": lol.reason,
        }

    params = state.get("normalised_params") or {}
    # target_table is resolved by data_architect and stored separately in
    # state; inject it into params so HTTPBackend forwards it to the CF
    # (which only writes to BQ when target_table is present in the payload).
    target_table = state.get("target_table")
    if target_table and "target_table" not in params:
        params = {**params, "target_table": target_table}
    tenant_id = state.get("tenant_id", "")
    lol = run(manifest, params, tenant_id)

    update: dict[str, Any] = {
        "node_results": [lol.model_dump()],
        "last_status": lol.status,
    }
    if lol.is_terminal_error():
        update["final_error"] = lol.reason
        return update

    update["connector_response"] = lol.data.get("connector", {})
    return update


__all__ = ["NODE_NAME", "run", "node"]
