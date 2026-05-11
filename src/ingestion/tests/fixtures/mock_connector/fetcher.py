"""Mock connector for tests. Returns canned data without any network I/O.

Mirrors the real connector contract::

    fetch(params, context) -> {
        "status":  "ok" | "partial" | "error",
        "code":    int,
        "records": list[dict] | dict,
        "meta":    dict,
        "errors":  list[str],
    }

Behaviour is controlled by special keys in ``params``:

* ``simulate_status``: override the returned ``status`` (default ``ok``).
* ``simulate_errors``: list of strings copied verbatim into ``errors``.
* ``simulate_row_count``: how many rows to emit (default 3).
"""

from __future__ import annotations

from typing import Any


def fetch(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    rows = []
    n = int(params.get("simulate_row_count", 3))
    for i in range(n):
        rows.append(
            {
                "id": f"row_{i}",
                "label": f"Row #{i}",
                "value": float(i) * 1.5,
                "tenant_seen": context.get("tenant_marker", "unknown"),
            }
        )
    return {
        "status": params.get("simulate_status", "ok"),
        "code": 200,
        "records": rows,
        "meta": {
            "params_seen": {k: v for k, v in params.items() if k != "simulate_errors"},
            "context_keys": sorted(context.keys()),
        },
        "errors": list(params.get("simulate_errors", [])),
    }
