"""request_validator — pure node that validates an incoming ingestion request.

Responsibilities
----------------
1. Resolve the requested ``manifest_id`` against the local catalog.
2. Validate ``params`` against the manifest's ``params`` declaration
   (required keys, optional defaults, ``one_of`` exclusivity, type
   coercion, range checks, enum/pattern checks, ``field_list``
   membership).
3. Produce ``selected_fields`` for the next node (data_architect):
   either the user's explicit list, or every ``selectable=true`` field
   if the user passed an empty/missing list.
4. Return a :class:`NodeLOL` with status ``OK`` or ``ERR``. When ERR,
   ``errors`` lists every problem found (we do not stop at the first).

This module is **pure** — no I/O beyond reading the in-memory catalog,
no LLM calls, no globals mutated. It is safe to call in tests.

Output payload (``data`` of the NodeLOL) on OK::

    {
        "manifest_id":      str,
        "tenant_id":        str,
        "manifest":         dict,           # full validated manifest
        "normalised_params": dict,          # defaults applied, types coerced
        "selected_fields":  list[str],
        "matched_one_of":   list[str] | None,
    }

See ``docs/migration-plan.md`` Fase 2.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Iterable

from ingestion.lol import NodeLOL
from ingestion.manifest import Catalog, get_default_catalog

NODE_NAME = "request_validator"

# Phase 5 — reserved "system" param keys.
#
# These keys are populated by the platform itself (not by the
# connector manifest), so the strict ``unknown params`` check below
# must allow them. They are passed through to downstream nodes
# verbatim: ``data_architect`` reads ``target_table`` to override the
# default bronze_pattern substitution; future system fields (e.g.
# ``priority``, ``dry_run``) belong here as well.
#
# Keeping the allow-list intentionally small means we still loudly
# reject typos in connector-specific params, which is the validator's
# main job.
_SYSTEM_PARAM_KEYS: frozenset[str] = frozenset({"target_table"})


# ---------------------------------------------------------------------------
# Param coercion & validation primitives
# ---------------------------------------------------------------------------

def _coerce_scalar(value: Any, declared_type: str) -> tuple[Any, str | None]:
    """Coerce ``value`` to the manifest-declared scalar type.

    Returns ``(coerced_value, error_or_none)``. We intentionally accept
    common string forms (e.g. "true", "2026-01-15") so the frontend can
    send JSON-friendly payloads without having to pre-convert.
    """
    if value is None:
        return None, None

    if declared_type == "string":
        if not isinstance(value, str):
            return value, f"expected string, got {type(value).__name__}"
        return value, None

    if declared_type == "integer":
        if isinstance(value, bool):  # bool is a subclass of int — reject
            return value, "expected integer, got boolean"
        if isinstance(value, int):
            return value, None
        if isinstance(value, str) and value.lstrip("-").isdigit():
            return int(value), None
        return value, f"expected integer, got {type(value).__name__}"

    if declared_type == "number":
        if isinstance(value, bool):
            return value, "expected number, got boolean"
        if isinstance(value, (int, float)):
            return float(value), None
        if isinstance(value, str):
            try:
                return float(value), None
            except ValueError:
                return value, f"could not parse '{value}' as number"
        return value, f"expected number, got {type(value).__name__}"

    if declared_type == "boolean":
        if isinstance(value, bool):
            return value, None
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true", None
        return value, f"expected boolean, got {type(value).__name__}"

    if declared_type == "date":
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.isoformat(), None
        if isinstance(value, str):
            try:
                date.fromisoformat(value)
                return value, None
            except ValueError:
                return value, f"could not parse '{value}' as ISO date (YYYY-MM-DD)"
        return value, f"expected ISO date string, got {type(value).__name__}"

    if declared_type == "datetime":
        if isinstance(value, datetime):
            return value.isoformat(), None
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value)
                return value, None
            except ValueError:
                return value, f"could not parse '{value}' as ISO datetime"
        return value, f"expected ISO datetime string, got {type(value).__name__}"

    if declared_type == "array":
        if isinstance(value, list):
            return value, None
        return value, f"expected array, got {type(value).__name__}"

    if declared_type == "object":
        if isinstance(value, dict):
            return value, None
        return value, f"expected object, got {type(value).__name__}"

    # 'field_list' is handled at a higher level (we need the manifest's
    # available_fields); here we only enforce the array shape.
    if declared_type == "field_list":
        if not isinstance(value, list):
            return value, f"expected list of field names, got {type(value).__name__}"
        bad = [item for item in value if not isinstance(item, str)]
        if bad:
            return value, f"field_list must contain only strings; bad entries: {bad!r}"
        return value, None

    # Unknown type — schema validation would have caught this earlier.
    return value, f"unsupported param type '{declared_type}'"


def _validate_constraints(
    name: str,
    value: Any,
    spec: dict[str, Any],
    errors: list[str],
) -> None:
    """Apply ``minimum``/``maximum``/``min_length``/``max_length``/``pattern``/``enum``.

    Mutates ``errors`` in place when constraints fail.
    """
    if value is None:
        return

    if "enum" in spec and value not in spec["enum"]:
        errors.append(
            f"params.{name}: value {value!r} not in enum {spec['enum']!r}"
        )

    if "minimum" in spec and isinstance(value, (int, float)):
        if value < spec["minimum"]:
            errors.append(
                f"params.{name}: {value} below minimum {spec['minimum']}"
            )
    if "maximum" in spec and isinstance(value, (int, float)):
        if value > spec["maximum"]:
            errors.append(
                f"params.{name}: {value} above maximum {spec['maximum']}"
            )

    if isinstance(value, str):
        if "min_length" in spec and len(value) < spec["min_length"]:
            errors.append(
                f"params.{name}: length {len(value)} below min_length {spec['min_length']}"
            )
        if "max_length" in spec and len(value) > spec["max_length"]:
            errors.append(
                f"params.{name}: length {len(value)} above max_length {spec['max_length']}"
            )
        if "pattern" in spec and not re.search(spec["pattern"], value):
            errors.append(
                f"params.{name}: value {value!r} does not match pattern {spec['pattern']!r}"
            )


# ---------------------------------------------------------------------------
# one_of resolution
# ---------------------------------------------------------------------------

def _resolve_one_of(
    one_of_groups: list[list[str]],
    provided: set[str],
) -> tuple[list[str] | None, str | None]:
    """Return the matched group (list of param names) or an error string.

    Rules:
    - If ``one_of_groups`` is empty, returns ``(None, None)`` (nothing to do).
    - A group matches when **all** of its names are in ``provided``.
    - Exactly one group must match. Zero or two-or-more matches → error.

    The matched group becomes ``state['matched_one_of']`` for the trace.
    """
    if not one_of_groups:
        return None, None

    fully_matched = [
        group for group in one_of_groups if all(name in provided for name in group)
    ]
    if len(fully_matched) == 1:
        return list(fully_matched[0]), None

    pretty = " | ".join("(" + ", ".join(g) + ")" for g in one_of_groups)
    if not fully_matched:
        return None, (
            f"params.one_of: no group fully provided. Expected exactly one of: {pretty}"
        )
    return None, (
        f"params.one_of: {len(fully_matched)} groups fully provided. "
        f"Exactly one is allowed. Groups: {pretty}"
    )


# ---------------------------------------------------------------------------
# Field list resolution
# ---------------------------------------------------------------------------

def _selectable_field_names(available_fields: Iterable[dict[str, Any]]) -> list[str]:
    """Return names of every field with ``selectable != False``."""
    return [
        f["name"]
        for f in available_fields
        if f.get("selectable", True) is not False
    ]


def _validate_field_list(
    requested: list[str],
    available_fields: list[dict[str, Any]],
    param_name: str,
    errors: list[str],
) -> list[str]:
    """Return the resolved field list. Empty input → all selectable fields."""
    available_names = {f["name"] for f in available_fields}

    if not requested:
        return _selectable_field_names(available_fields)

    unknown = [name for name in requested if name not in available_names]
    if unknown:
        errors.append(
            f"params.{param_name}: unknown fields {unknown!r}. "
            f"See manifest.available_fields."
        )

    seen: set[str] = set()
    deduped: list[str] = []
    for name in requested:
        if name in seen or name not in available_names:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_request(
    manifest_id: str,
    params: dict[str, Any],
    tenant_id: str,
    *,
    catalog: Catalog | None = None,
) -> NodeLOL:
    """Pure function: validate a request against a manifest.

    Parameters
    ----------
    manifest_id:
        Globally unique manifest id (matches ``manifest.id``).
    params:
        Raw parameters from the API request body.
    tenant_id:
        Tenant identifier. Not resolved here (that happens in
        ``connector_runner``); we only check it is a non-empty string.
    catalog:
        Optional catalog override. Defaults to
        :func:`ingestion.manifest.get_default_catalog` so production
        callers don't need to thread it through.
    """
    errors: list[str] = []

    if not isinstance(manifest_id, str) or not manifest_id:
        errors.append("manifest_id: must be a non-empty string")
    if not isinstance(tenant_id, str) or not tenant_id:
        errors.append("tenant_id: must be a non-empty string")
    if not isinstance(params, dict):
        errors.append(f"params: expected object, got {type(params).__name__}")
        # No point continuing with an unusable params object.
        return NodeLOL.err(NODE_NAME, "request shape invalid", errors)

    if errors:
        return NodeLOL.err(NODE_NAME, "request shape invalid", errors)

    cat = catalog if catalog is not None else get_default_catalog()
    manifest = cat.get(manifest_id)
    if manifest is None:
        return NodeLOL.err(
            NODE_NAME,
            f"manifest_id '{manifest_id}' not found in catalog",
            [f"manifest_id: '{manifest_id}' not in catalog"],
            data={"manifest_id": manifest_id},
        )

    declared_params = manifest.get("params", {}) or {}
    required_specs: list[dict[str, Any]] = list(declared_params.get("required", []))
    optional_specs: list[dict[str, Any]] = list(declared_params.get("optional", []))
    one_of_groups: list[list[str]] = list(declared_params.get("one_of", []))

    spec_by_name: dict[str, dict[str, Any]] = {
        s["name"]: s for s in (*required_specs, *optional_specs) if "name" in s
    }
    declared_names = set(spec_by_name.keys())
    required_names = {s["name"] for s in required_specs if "name" in s}

    # Reject unknown params — the manifest is authoritative — EXCEPT for
    # the reserved "system" keys that the platform itself populates from
    # request-level fields (Phase 5). The frontend exposes
    # ``target_table`` as an override on the run form, so it shows up
    # inside ``params`` from the wire's POV but is not part of any
    # manifest's params schema. Treating it as "known" here lets the
    # validator stay strict for connector-specific params without
    # forcing every manifest to re-declare the same boilerplate.
    unknown = [
        name
        for name in params.keys()
        if name not in declared_names and name not in _SYSTEM_PARAM_KEYS
    ]
    if unknown:
        errors.append(
            f"params: unknown keys {unknown!r}. Allowed: {sorted(declared_names)!r}"
        )

    # Required keys must be present.
    missing = [name for name in required_names if name not in params]
    if missing:
        errors.append(f"params: missing required keys {missing!r}")

    # Coerce + constraint-check every declared key (skip unknowns above).
    normalised: dict[str, Any] = {}
    selected_fields: list[str] = []
    for name, spec in spec_by_name.items():
        declared_type = spec.get("type", "string")
        if name in params:
            coerced, err = _coerce_scalar(params[name], declared_type)
            if err is not None:
                errors.append(f"params.{name}: {err}")
                continue
            _validate_constraints(name, coerced, spec, errors)
            normalised[name] = coerced
        elif "default" in spec and name not in required_names:
            normalised[name] = spec["default"]

    # Resolve field_list params (typically "fields") against available_fields.
    available_fields = list(manifest.get("available_fields", []))
    for name, spec in spec_by_name.items():
        if spec.get("type") != "field_list":
            continue
        requested = normalised.get(name, [])
        if not isinstance(requested, list):
            # _coerce_scalar already errored; skip.
            continue
        resolved = _validate_field_list(requested, available_fields, name, errors)
        normalised[name] = resolved
        # Convention: a param literally named "fields" drives selected_fields.
        # Other field_list params can exist but won't be used downstream.
        if name == "fields":
            selected_fields = resolved

    # Apply one_of exclusivity AFTER coercion so we know exactly which
    # keys were *meaningfully* provided (defaults applied are excluded).
    provided_keys = {name for name in spec_by_name if name in params}
    matched_one_of, one_of_err = _resolve_one_of(one_of_groups, provided_keys)
    if one_of_err:
        errors.append(one_of_err)

    if errors:
        return NodeLOL.err(
            NODE_NAME,
            f"validation failed for manifest '{manifest_id}' ({len(errors)} error(s))",
            errors,
            data={"manifest_id": manifest_id, "tenant_id": tenant_id},
        )

    # No "fields" param declared → caller did not request a subset; default
    # to every selectable field so data_architect has something to work with.
    if not selected_fields:
        selected_fields = _selectable_field_names(available_fields)

    return NodeLOL.ok(
        NODE_NAME,
        reason=(
            f"manifest '{manifest_id}' validated; "
            f"{len(selected_fields)} field(s) selected"
        ),
        data={
            "manifest_id": manifest_id,
            "tenant_id": tenant_id,
            "manifest": manifest,
            "normalised_params": normalised,
            "selected_fields": selected_fields,
            "matched_one_of": matched_one_of,
        },
    )


# ---------------------------------------------------------------------------
# LangGraph node wrapper
# ---------------------------------------------------------------------------

def node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph entrypoint: read inputs from state, write LOL + intermediate keys.

    The wrapper is intentionally thin: it delegates to
    :func:`validate_request` and projects the OK payload into typed state
    keys consumed by the next node. ERR short-circuits via
    ``last_status`` / ``final_error``.
    """
    lol = validate_request(
        manifest_id=state.get("manifest_id", ""),
        params=state.get("params", {}) or {},
        tenant_id=state.get("tenant_id", ""),
    )
    update: dict[str, Any] = {
        "node_results": [lol.model_dump()],
        "last_status": lol.status,
    }
    if lol.is_terminal_error():
        update["final_error"] = lol.reason
        return update

    payload = lol.data
    update.update(
        {
            "manifest": payload["manifest"],
            "normalised_params": payload["normalised_params"],
            "selected_fields": payload["selected_fields"],
            "matched_one_of": payload["matched_one_of"],
        }
    )
    return update


__all__ = ["NODE_NAME", "validate_request", "node"]
