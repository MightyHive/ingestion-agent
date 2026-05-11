"""Lightweight LOL contract for deterministic ingestion nodes.

The legacy multi-agent platform uses ``shared/lol/__init__.py`` with one
heavily-typed Pydantic model per agent. The deterministic pipeline does
not need that level of polymorphism: each node is pure, its inputs and
outputs are exhaustively documented in the manifest schema, and the
node-specific structured output lives under ``data``.

This module exposes a single :class:`NodeLOL` model used by every
ingestion node. The motivation is:

* Keep the contract narrow so future maintainers do not need to learn
  one Pydantic class per node.
* Make the event bus trivially serialisable (every entry has the same
  shape).
* Preserve the OK / WARN / ERR semantics from the LOL Protocol so
  downstream observability can keep treating them as first-class.

See ``docs/architecture.md`` §3 (LOL Protocol).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

NodeStatus = Literal["OK", "WARN", "ERR"]


class NodeLOL(BaseModel):
    """Single LOL envelope used by every deterministic ingestion node.

    Attributes
    ----------
    node:
        Stable identifier of the node that emitted this LOL. Matches the
        node name registered in :mod:`src.ingestion.graph`.
    status:
        Operation status. ``OK`` (success), ``WARN`` (succeeded with
        caveats — for example, the connector returned partial data) or
        ``ERR`` (the node failed; the graph routes to ``END``).
    reason:
        Human-readable, single-line summary. Surfaced in the trace and
        in the API response when the run fails.
    data:
        Node-specific structured output. Each node documents the keys it
        produces in its module docstring. The schema is deliberately
        loose at this layer — strict typing happens inside each node's
        pure function before the LOL is built.
    errors:
        Detailed validation errors (one entry per problem). Populated
        only when ``status`` is ``ERR``; remains empty otherwise.
    """

    node: str = Field(description="Stable id of the emitting node.")
    status: NodeStatus = Field(description="OK, WARN, or ERR.")
    reason: str = Field(description="Single-line human summary.")
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Node-specific structured output (see node docstring).",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Detailed errors when status=ERR. Empty otherwise.",
    )

    @classmethod
    def ok(cls, node: str, reason: str, data: dict[str, Any] | None = None) -> "NodeLOL":
        """Convenience constructor for OK results."""
        return cls(node=node, status="OK", reason=reason, data=data or {})

    @classmethod
    def warn(
        cls,
        node: str,
        reason: str,
        data: dict[str, Any] | None = None,
        errors: list[str] | None = None,
    ) -> "NodeLOL":
        """Convenience constructor for WARN results (partial success)."""
        return cls(
            node=node,
            status="WARN",
            reason=reason,
            data=data or {},
            errors=errors or [],
        )

    @classmethod
    def err(
        cls,
        node: str,
        reason: str,
        errors: list[str] | None = None,
        data: dict[str, Any] | None = None,
    ) -> "NodeLOL":
        """Convenience constructor for ERR results."""
        return cls(
            node=node,
            status="ERR",
            reason=reason,
            data=data or {},
            errors=errors or [],
        )

    def is_terminal_error(self) -> bool:
        """Return True if the graph should route to END after this LOL."""
        return self.status == "ERR"


__all__ = ["NodeLOL", "NodeStatus"]
