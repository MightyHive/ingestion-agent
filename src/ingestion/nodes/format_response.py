"""format_response — shape the connector's raw output for the frontend.

Phase 2 scope
-------------
The MVP **does not write to BigQuery yet**. This node only normalises
the ``ConnectorResponse`` into the shape the frontend's preview pane
expects, plus the previously-computed DDL so Mili's UI can show:

* table name + column list (preview header)
* sample rows (preview body)
* run-level metadata (counts, partial flags)

BigQuery loading lands in Fase 5 (HTTPBackend + Cloud Function side).
We keep the node here so the pipeline contract stays stable across
phases — when BQ loading turns on, only the *body* of this node
changes; ``state['formatted_response']`` keeps the same shape.

Output shape
------------
::

    {
        "manifest_id":   str,
        "tenant_id":     str,
        "target_table":  str,            # from data_architect
        "ddl":           str,            # from data_architect
        "columns":       list[str],
        "row_count":     int,
        "rows_preview":  list[dict],     # first PREVIEW_ROWS rows
        "meta":          dict,           # from connector
        "errors":        list[str],      # connector-level non-fatal errors
        "diagnostics":   dict,
    }

Records selection
-----------------
The connector's ``records`` field is connector-specific. Manifests can
declare a ``metadata.response_subkey`` (e.g. Meta sets ``"ads"``) to
tell us which sub-list of ``records`` is the canonical row stream.
Without it, we accept either:

* a list of dicts → used directly,
* a dict with a single list value → that list,
* anything else → kept as-is, with an empty preview.
"""

from __future__ import annotations

from typing import Any

from ingestion.lol import NodeLOL

NODE_NAME = "format_response"
PREVIEW_ROWS = 25


def _select_records_stream(
    records: Any, response_subkey: str | None
) -> tuple[list[dict[str, Any]], str | None]:
    """Return ``(rows, note)``. ``note`` is non-None when we couldn't infer.

    ``note`` is surfaced as a WARN reason; it does not fail the run.
    """
    if records is None:
        return [], "connector.records was None"

    if isinstance(records, list):
        return [r for r in records if isinstance(r, dict)], None

    if isinstance(records, dict):
        if response_subkey and response_subkey in records:
            stream = records[response_subkey]
            if isinstance(stream, list):
                return [r for r in stream if isinstance(r, dict)], None
            return [], (
                f"records['{response_subkey}'] was {type(stream).__name__}, "
                f"expected list"
            )
        list_subkeys = [k for k, v in records.items() if isinstance(v, list)]
        if len(list_subkeys) == 1:
            stream = records[list_subkeys[0]]
            return [r for r in stream if isinstance(r, dict)], None
        return [], (
            "records is a dict with multiple list keys "
            f"({list_subkeys!r}); manifest.metadata.response_subkey is required."
        )

    return [], (
        f"records was {type(records).__name__}, expected list or dict"
    )


def format_response(
    manifest: dict[str, Any],
    selected_fields: list[str],
    target_table: str,
    ddl: str,
    connector_response: dict[str, Any],
    tenant_id: str,
) -> NodeLOL:
    """Pure function. Returns OK or WARN (never ERR — we already have data)."""
    response_subkey = (manifest.get("metadata") or {}).get("response_subkey")
    rows, note = _select_records_stream(
        connector_response.get("records"), response_subkey
    )

    formatted = {
        "manifest_id": manifest.get("id"),
        "tenant_id": tenant_id,
        "target_table": target_table,
        "ddl": ddl,
        "columns": list(selected_fields),
        "row_count": len(rows),
        "rows_preview": rows[:PREVIEW_ROWS],
        "meta": dict(connector_response.get("meta") or {}),
        "errors": list(connector_response.get("errors") or []),
        "diagnostics": dict(connector_response.get("diagnostics") or {}),
    }

    if note:
        return NodeLOL.warn(
            NODE_NAME,
            reason=f"records normalised with caveat: {note}",
            data={"formatted_response": formatted},
            errors=[note],
        )
    return NodeLOL.ok(
        NODE_NAME,
        reason=(
            f"formatted {len(rows)} row(s) for table {target_table}"
            f" ({len(selected_fields)} column(s))"
        ),
        data={"formatted_response": formatted},
    )


# ---------------------------------------------------------------------------
# LangGraph node wrapper
# ---------------------------------------------------------------------------

def node(state: dict[str, Any]) -> dict[str, Any]:
    manifest = state.get("manifest") or {}
    selected_fields = state.get("selected_fields") or []
    target_table = state.get("target_table") or ""
    ddl = state.get("ddl") or ""
    connector_response = state.get("connector_response") or {}
    tenant_id = state.get("tenant_id", "")
    lol = format_response(
        manifest,
        selected_fields,
        target_table,
        ddl,
        connector_response,
        tenant_id,
    )
    update: dict[str, Any] = {
        "node_results": [lol.model_dump()],
        "last_status": lol.status,
        "formatted_response": lol.data.get("formatted_response"),
    }
    return update


__all__ = ["NODE_NAME", "PREVIEW_ROWS", "format_response", "node"]
