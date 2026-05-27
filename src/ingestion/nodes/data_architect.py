"""data_architect — deterministic BigQuery DDL generator.

Replaces the legacy LLM-driven Data Architect agent. Given a validated
manifest and the user's selected_fields, this node emits a stable
``CREATE TABLE IF NOT EXISTS`` statement that BigQuery accepts.

The legacy agent produced DDL by prompting an LLM with the manifest +
catalog. That introduced two failure modes we no longer accept:

1. **Non-determinism** — the same input could yield different DDL on
   reruns, breaking diff-based reviews and CI gates.
2. **Type drift** — the LLM occasionally normalised types (e.g.
   ``NUMERIC`` → ``FLOAT64``) silently. The manifest is now the single
   source of truth and we emit types verbatim.

DDL contract
------------
The generated statement always:

* Uses ``CREATE TABLE IF NOT EXISTS`` (idempotent).
* Includes every selected column plus any ``selectable=false`` columns
  (the manifest can mark partition keys as non-selectable so the user
  cannot omit them from the table).
* Applies the column ``mode`` (NULLABLE/REQUIRED/REPEATED).
* Adds ``OPTIONS(description="...")`` when the field has a description.
* Honours ``table_naming.partition_field`` and ``table_naming.partition_type``.
* Honours ``table_naming.clustering_fields`` (BigQuery max 4).
* Substitutes ``bronze_pattern`` tokens: ``{platform}``, ``{connector}``,
  ``{id}``, ``{version_major}``.

Output payload (``NodeLOL.data``) on OK::

    {
        "ddl":          str,
        "target_table": str,           # resolved table name (bronze.<id> by default)
        "columns":      list[dict],    # what the DDL declared, for the trace
    }

See ``docs/architecture.md`` §3 and ``src/ingestion/manifest/schema.json`` for the type rules.
"""

from __future__ import annotations

import re
from typing import Any

from ingestion.lol import NodeLOL

NODE_NAME = "data_architect"

# BigQuery types accepted in DDL. Mirrors schema.json's enum.
# Kept as a frozenset so unknown types short-circuit before we emit.
_VALID_BQ_TYPES = frozenset(
    {
        "STRING",
        "INT64",
        "FLOAT64",
        "NUMERIC",
        "BIGNUMERIC",
        "BOOL",
        "DATE",
        "DATETIME",
        "TIMESTAMP",
        "TIME",
        "BYTES",
        "JSON",
        "GEOGRAPHY",
    }
)
# ARRAY/STRUCT need their inner type/fields and are emitted via _render_complex_type.
_COMPLEX_BQ_TYPES = frozenset({"ARRAY", "STRUCT"})


def _escape_bq_string(value: str) -> str:
    """Escape a string literal so it's safe inside ``"..."`` in BigQuery."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _render_complex_type(field: dict[str, Any]) -> str:
    """Render an ARRAY/STRUCT type spec recursively."""
    declared = field["type"]
    if declared == "ARRAY":
        inner = field.get("items_type")
        if not inner:
            raise ValueError(
                f"field '{field.get('name')}' has type=ARRAY but no items_type"
            )
        # Allow nested STRUCT-of-array via items_type='STRUCT' + fields.
        if inner == "STRUCT":
            return f"ARRAY<{_render_complex_type({**field, 'type': 'STRUCT'})}>"
        if inner not in _VALID_BQ_TYPES:
            raise ValueError(
                f"field '{field.get('name')}' has unsupported items_type '{inner}'"
            )
        return f"ARRAY<{inner}>"
    if declared == "STRUCT":
        nested = field.get("fields") or []
        if not nested:
            raise ValueError(
                f"field '{field.get('name')}' has type=STRUCT but no nested fields"
            )
        rendered = [
            f"{nf['name']} {_render_field_type(nf)}" for nf in nested
        ]
        return f"STRUCT<{', '.join(rendered)}>"
    raise ValueError(f"unsupported complex type '{declared}'")


def _render_field_type(field: dict[str, Any]) -> str:
    """Return the type expression for a single field (scalar or complex)."""
    declared = field["type"]
    if declared in _VALID_BQ_TYPES:
        return declared
    if declared in _COMPLEX_BQ_TYPES:
        return _render_complex_type(field)
    raise ValueError(
        f"field '{field.get('name')}' has unsupported type '{declared}'"
    )


def _render_column(field: dict[str, Any]) -> str:
    """Render one column line, including mode and OPTIONS(description)."""
    name = field["name"]
    type_expr = _render_field_type(field)
    mode = field.get("mode", "NULLABLE")
    parts = [f"  {name} {type_expr}"]
    if mode == "REQUIRED":
        parts.append("NOT NULL")
    elif mode == "REPEATED":
        # In standard SQL DDL, REPEATED is expressed by ARRAY<T>, but
        # BigQuery also accepts the legacy ``REPEATED`` keyword on
        # scalars. We prefer the array form for correctness; if a
        # manifest sets mode=REPEATED on a scalar, upgrade the type.
        if not type_expr.startswith("ARRAY<"):
            parts[0] = f"  {name} ARRAY<{type_expr}>"
    description = field.get("description")
    if description:
        parts.append(f'OPTIONS(description="{_escape_bq_string(description)}")')
    return " ".join(parts)


def _resolve_table_name(
    manifest: dict[str, Any], *, tenant_id: str | None = None
) -> str:
    """Substitute bronze_pattern tokens.

    Tokens: ``{platform}``, ``{connector}``, ``{id}``, ``{version_major}``,
    ``{tenant_id}``. Default pattern is ``bronze.{id}`` per schema.json.

    The ``{tenant_id}`` token was added in Phase 5 so that a single
    connector deployment can land each tenant's data into its own
    BigQuery table (``bronze.meta_facebook_ad_insights_cliente1`` /
    ``..._cliente2``). When the manifest's ``bronze_pattern`` does not
    reference ``{tenant_id}``, this parameter is ignored — backwards
    compatible with the Phase 3/4 single-tenant layout.

    ``tenant_id`` is sanitised lightly (lowercased; ``-``/spaces → ``_``)
    so it produces a valid BigQuery identifier. We keep it minimal so
    that operators can audit the mapping from ``tenants.json`` to the
    table name at a glance.
    """
    pattern = (manifest.get("table_naming") or {}).get(
        "bronze_pattern", "bronze.{id}"
    )
    version = manifest.get("version", "0.0.0")
    version_major = re.split(r"[.+-]", version, maxsplit=1)[0]
    tokens = {
        "platform": manifest.get("platform", ""),
        "connector": manifest.get("connector", ""),
        "id": manifest["id"],
        "version_major": version_major,
        "tenant_id": _sanitise_bq_token(tenant_id or ""),
    }
    try:
        return pattern.format(**tokens)
    except KeyError as exc:
        raise ValueError(
            f"unknown token {exc!s} in bronze_pattern '{pattern}'. "
            f"Allowed: {sorted(tokens)!r}"
        ) from exc


def _sanitise_bq_token(value: str) -> str:
    """Normalise a string for safe substitution into a BQ table identifier.

    BigQuery identifiers accept ``[A-Za-z0-9_]``. We lowercase, replace
    spaces/dashes with underscores, and drop everything else. We do NOT
    raise here — the validator (or BQ itself) will reject a fully empty
    or otherwise pathological table name downstream, and we want this
    helper to stay side-effect-free for unit tests.
    """
    cleaned = value.strip().lower().replace("-", "_").replace(" ", "_")
    return "".join(ch for ch in cleaned if ch.isalnum() or ch == "_")


def _resolve_columns(
    manifest: dict[str, Any],
    selected_fields: list[str],
) -> list[dict[str, Any]]:
    """Return the columns the DDL must declare.

    Combines the user's selected fields with any non-selectable fields
    (e.g. partition keys flagged ``selectable=false`` in the manifest).
    Order: manifest declaration order, so the DDL is stable across runs.
    """
    selected = set(selected_fields)
    columns: list[dict[str, Any]] = []
    seen: set[str] = set()
    for field in manifest.get("available_fields", []):
        name = field["name"]
        if name in seen:
            continue
        if name in selected or field.get("selectable", True) is False:
            columns.append(field)
            seen.add(name)
    return columns


def to_ddl(
    manifest: dict[str, Any],
    selected_fields: list[str],
    *,
    table_target: str | None = None,
    tenant_id: str | None = None,
) -> tuple[str, str, list[dict[str, Any]]]:
    """Emit the BigQuery ``CREATE TABLE`` for a manifest + selection.

    Parameters
    ----------
    manifest:
        Validated manifest dict (already went through the JSON-Schema
        validator in :mod:`ingestion.manifest.loader`).
    selected_fields:
        Names of fields the user wants. Non-selectable fields are
        included automatically.
    table_target:
        Optional explicit fully-qualified table name. Takes precedence
        over the manifest's ``bronze_pattern`` substitution. The
        frontend exposes this via ``params.target_table`` so the user
        can override the default table name (e.g. to land in a
        sandbox dataset for a one-off backfill).
    tenant_id:
        Used to substitute the ``{tenant_id}`` token in
        ``bronze_pattern``. Only consulted when ``table_target`` is
        not provided. See :func:`_resolve_table_name`.

    Returns
    -------
    ``(ddl_text, resolved_table_name, declared_columns)``.

    Raises
    ------
    ValueError:
        When the manifest references an unsupported BQ type or an
        unknown bronze_pattern token. The validator should normally
        have caught these; we re-raise so the bug is loud.
    """
    table = table_target or _resolve_table_name(manifest, tenant_id=tenant_id)
    columns = _resolve_columns(manifest, selected_fields)
    if not columns:
        raise ValueError(
            "no columns to declare — selected_fields was empty and the "
            "manifest has no non-selectable fields either"
        )

    rendered_columns = [_render_column(col) for col in columns]
    table_naming = manifest.get("table_naming") or {}

    suffixes: list[str] = []
    partition_field = table_naming.get("partition_field")
    if partition_field:
        partition_type = table_naming.get("partition_type", "DAY")
        # BigQuery accepts PARTITION BY <expr>. For DAY we use the field
        # directly (TIMESTAMP/DATE); for HOUR/MONTH/YEAR we wrap with
        # the appropriate truncation function.
        if partition_type == "DAY":
            suffixes.append(f"PARTITION BY {partition_field}")
        elif partition_type == "HOUR":
            suffixes.append(f"PARTITION BY TIMESTAMP_TRUNC({partition_field}, HOUR)")
        elif partition_type == "MONTH":
            suffixes.append(f"PARTITION BY DATE_TRUNC({partition_field}, MONTH)")
        elif partition_type == "YEAR":
            suffixes.append(f"PARTITION BY DATE_TRUNC({partition_field}, YEAR)")
        else:
            raise ValueError(
                f"unsupported partition_type '{partition_type}'. "
                f"Allowed: DAY, HOUR, MONTH, YEAR."
            )
    clustering_fields = table_naming.get("clustering_fields") or []
    if clustering_fields:
        if len(clustering_fields) > 4:
            raise ValueError(
                f"clustering_fields has {len(clustering_fields)} entries; "
                f"BigQuery allows up to 4."
            )
        suffixes.append("CLUSTER BY " + ", ".join(clustering_fields))

    ddl_lines = [
        f"CREATE TABLE IF NOT EXISTS `{table}` (",
        ",\n".join(rendered_columns),
        ")",
    ]
    if suffixes:
        ddl_lines.append("\n".join(suffixes))
    ddl_text = "\n".join(ddl_lines).rstrip() + ";\n"
    return ddl_text, table, columns


# ---------------------------------------------------------------------------
# LangGraph node wrapper
# ---------------------------------------------------------------------------

def node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph entrypoint. Reads ``manifest`` + ``selected_fields``.

    Phase 5 additions:

    * ``params.target_table`` (user override from the frontend) is
      forwarded as ``table_target`` so it wins over the manifest
      substitution.
    * ``state.tenant_id`` feeds the ``{tenant_id}`` token of
      ``bronze_pattern`` so multi-tenant deployments land in
      per-tenant tables by default.
    """
    manifest = state.get("manifest")
    selected_fields = state.get("selected_fields") or []
    tenant_id = state.get("tenant_id")
    params = state.get("params") or {}
    user_target = params.get("target_table")
    user_target = user_target.strip() if isinstance(user_target, str) else None
    if not user_target:
        user_target = None
    if not manifest:
        # Validator should have populated this; guard anyway.
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
    try:
        ddl_text, table, columns = to_ddl(
            manifest,
            selected_fields,
            table_target=user_target,
            tenant_id=tenant_id,
        )
    except ValueError as exc:
        lol = NodeLOL.err(
            NODE_NAME,
            f"DDL generation failed: {exc}",
            [str(exc)],
            data={"manifest_id": manifest.get("id"), "selected_fields": selected_fields},
        )
        return {
            "node_results": [lol.model_dump()],
            "last_status": lol.status,
            "final_error": lol.reason,
        }

    lol = NodeLOL.ok(
        NODE_NAME,
        reason=(
            f"DDL ready for {table} ({len(columns)} columns)"
        ),
        data={
            "ddl": ddl_text,
            "target_table": table,
            "columns": [
                {"name": c["name"], "type": c["type"], "mode": c.get("mode", "NULLABLE")}
                for c in columns
            ],
        },
    )
    return {
        "node_results": [lol.model_dump()],
        "last_status": lol.status,
        "ddl": ddl_text,
        "target_table": table,
    }


__all__ = ["NODE_NAME", "to_ddl", "node"]
