"""MDS deterministic ingestion pipeline.

This package replaces the multi-agent LLM ingestion graph (src/agents/*)
with a deterministic pipeline that consumes manifests from the
``connectors-library`` git submodule.

Public surface (Fase 2):

* :class:`ingestion.lol.NodeLOL` — light LOL envelope used by every node.
* :class:`ingestion.state.IngestionState` — TypedDict for the new graph.
* :func:`ingestion.graph.build_graph` — compiled LangGraph.
* :func:`ingestion.graph.run_ingestion` — sync convenience wrapper.
* :mod:`ingestion.manifest` — Fase 1 catalog + loader.

See ``docs/architecture.md`` for the design.
"""

from ingestion.graph import build_graph, run_ingestion
from ingestion.lol import NodeLOL, NodeStatus
from ingestion.state import IngestionState

__all__ = [
    "IngestionState",
    "NodeLOL",
    "NodeStatus",
    "build_graph",
    "run_ingestion",
]
