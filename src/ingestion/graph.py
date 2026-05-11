"""LangGraph wiring for the deterministic ingestion pipeline.

Topology
--------
::

    START
      │
      ▼
    request_validator
      │
      ├── status=ERR ───────────────────────────────────────► END
      │
      ▼
    data_architect
      │
      ├── status=ERR ───────────────────────────────────────► END
      │
      ▼
    connector_runner
      │
      ├── status=ERR ───────────────────────────────────────► END
      │
      ▼
    format_response
      │
      ▼
    END

Every node returns a :class:`ingestion.lol.NodeLOL`. The conditional
router checks ``state['last_status']`` and routes to ``END`` whenever it
reads ``ERR``. ``WARN`` and ``OK`` continue down the happy path.

Why no fan-out
--------------
The legacy graph used coordinator-driven parallel fan-out to several
LLM agents (data_architect, software_engineer, api_researcher).
Deterministic ingestion has no such parallelism: each node depends on
the previous one's output. We keep the graph linear so the trace and
self-correction story remain trivially auditable.

Public API
----------
* :func:`build_graph`: returns a *compiled* StateGraph ready to invoke.
* :func:`run_ingestion`: convenience sync wrapper that builds + invokes
  with a fresh state. Used by tests and the smoke script. The API
  layer (Phase 3) will wire its own caller.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from ingestion.nodes import (
    connector_runner,
    data_architect,
    format_response,
    request_validator,
)
from ingestion.state import IngestionState


def _route_after(node_name: str):
    """Build a router callable for the conditional edge after ``node_name``.

    Returning ``END`` short-circuits the rest of the pipeline whenever
    the most recent LOL was an ERR.
    """

    def _router(state: dict[str, Any]) -> str:
        if state.get("last_status") == "ERR":
            return END
        return _NEXT_NODE[node_name]

    return _router


_NEXT_NODE = {
    request_validator.NODE_NAME: data_architect.NODE_NAME,
    data_architect.NODE_NAME: connector_runner.NODE_NAME,
    connector_runner.NODE_NAME: format_response.NODE_NAME,
    format_response.NODE_NAME: END,
}


def build_graph():
    """Construct and compile the deterministic ingestion graph.

    Compilation is deliberately uncached: the graph is stateless and
    cheap to build, and tests mutate the dispatcher / catalog between
    runs. Phase 3 will wire a single compiled instance into the API
    process when stability requirements demand it.
    """
    builder = StateGraph(IngestionState)

    builder.add_node(request_validator.NODE_NAME, request_validator.node)
    builder.add_node(data_architect.NODE_NAME, data_architect.node)
    builder.add_node(connector_runner.NODE_NAME, connector_runner.node)
    builder.add_node(format_response.NODE_NAME, format_response.node)

    builder.add_edge(START, request_validator.NODE_NAME)

    for node_name in (
        request_validator.NODE_NAME,
        data_architect.NODE_NAME,
        connector_runner.NODE_NAME,
    ):
        next_node = _NEXT_NODE[node_name]
        builder.add_conditional_edges(
            node_name,
            _route_after(node_name),
            {next_node: next_node, END: END},
        )

    builder.add_edge(format_response.NODE_NAME, END)
    return builder.compile()


def run_ingestion(
    *, manifest_id: str, params: dict[str, Any], tenant_id: str
) -> dict[str, Any]:
    """Sync convenience wrapper.

    Returns the final ``IngestionState``. Tests use this; the API layer
    will switch to the async equivalent in Phase 3.
    """
    graph = build_graph()
    initial_state: dict[str, Any] = {
        "manifest_id": manifest_id,
        "params": params,
        "tenant_id": tenant_id,
        "node_results": [],
        "obs_usages": [],
    }
    return graph.invoke(initial_state)


__all__ = ["build_graph", "run_ingestion"]
