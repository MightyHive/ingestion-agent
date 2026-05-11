"""Deterministic graph nodes for the ingestion pipeline.

Each node is a pure function (or thin LangGraph wrapper around one)
that takes a typed input, returns a :class:`ingestion.lol.NodeLOL`,
and never calls an LLM.

Nodes in topological order:

* :mod:`ingestion.nodes.request_validator`
* :mod:`ingestion.nodes.data_architect` (Manifest.to_ddl)
* :mod:`ingestion.nodes.connector_runner`
* :mod:`ingestion.nodes.format_response`

Wired together in :mod:`ingestion.graph`.
"""

from ingestion.nodes import (
    connector_runner,
    data_architect,
    format_response,
    request_validator,
)

__all__ = [
    "connector_runner",
    "data_architect",
    "format_response",
    "request_validator",
]
